//! axum の Router (api.md A-1〜A-6)。

use std::sync::Arc;
use std::time::Duration;

use axum::body::Body;
use axum::extract::rejection::QueryRejection;
use axum::extract::{Query, State};
use axum::http::{HeaderValue, Method, StatusCode, header};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::{Json, Router};
use chrono::Utc;
use feedgen_core::generator::Outcome;
use serde_json::json;
use tokio::sync::Semaphore;
use tower_http::cors::{Any, CorsLayer};

use crate::headers::encode_title;
use crate::query::{ApiError, parse_feed_query};
use crate::service::FeedService;

const RSS_CONTENT_TYPE: &str = "application/rss+xml; charset=utf-8";

/// 構成値。本番は 60 秒と 32 件。テストでは短い値を差し込む。
#[derive(Debug, Clone)]
pub struct AppConfig {
    pub timeout: Duration,
    pub max_concurrent: usize,
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            timeout: Duration::from_secs(60),
            max_concurrent: 32,
        }
    }
}

struct Inner<S> {
    service: Arc<S>,
    timeout: Duration,
    permits: Arc<Semaphore>,
}

pub fn router<S: FeedService>(service: Arc<S>, config: AppConfig) -> Router {
    let inner = Arc::new(Inner {
        service,
        timeout: config.timeout,
        permits: Arc::new(Semaphore::new(config.max_concurrent)),
    });
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods([Method::GET])
        .allow_headers(Any);
    Router::new()
        .route("/", get(root))
        .route("/health", get(health))
        .route("/feed", get(feed::<S>))
        .method_not_allowed_fallback(method_not_allowed)
        .fallback(not_found)
        .with_state(inner)
        .layer(cors)
}

fn error(status: StatusCode, detail: &str) -> Response {
    (status, Json(json!({ "detail": detail }))).into_response()
}

async fn root() -> Response {
    Json(json!({
        "name": "feedgen API",
        "version": env!("CARGO_PKG_VERSION"),
        "description": "URL から RSS を生成する",
        "endpoints": {
            "/feed": "GET。url から RSS を返す",
            "/health": "GET。死活確認",
        },
    }))
    .into_response()
}

async fn health() -> Response {
    Json(json!({ "status": "healthy", "service": "feedgen API" })).into_response()
}

async fn not_found() -> Response {
    error(StatusCode::NOT_FOUND, "Not Found")
}

async fn method_not_allowed() -> Response {
    error(StatusCode::METHOD_NOT_ALLOWED, "Method Not Allowed")
}

async fn feed<S: FeedService>(
    State(inner): State<Arc<Inner<S>>>,
    query: Result<Query<Vec<(String, String)>>, QueryRejection>,
) -> Response {
    let Ok(Query(pairs)) = query else {
        return error(StatusCode::BAD_REQUEST, "クエリを解釈できません");
    };
    let request = match parse_feed_query(&pairs) {
        Ok(request) => request,
        Err(ApiError { status, detail }) => return error(status, &detail),
    };
    let Ok(_permit) = inner.permits.clone().try_acquire_owned() else {
        return error(
            StatusCode::SERVICE_UNAVAILABLE,
            "混雑しています。しばらくしてから再度お試しください",
        );
    };

    let now = Utc::now().fixed_offset();
    let service = inner.service.clone();
    // 別タスクで動かし、panic を JoinError として受け、締切で中断できるようにする。
    let mut task =
        tokio::spawn(async move { service.generate(&request.url, &request.options, now).await });
    let joined = match tokio::time::timeout(inner.timeout, &mut task).await {
        Ok(joined) => joined,
        Err(_) => {
            task.abort();
            return error(StatusCode::GATEWAY_TIMEOUT, "処理に時間がかかりすぎました");
        }
    };
    match joined {
        Ok(Ok(outcome)) => success(outcome, now),
        Ok(Err(failure)) => error(StatusCode::BAD_REQUEST, &failure.to_string()),
        Err(failure) => {
            eprintln!("内部エラー: {failure}");
            error(StatusCode::INTERNAL_SERVER_ERROR, "Internal server error")
        }
    }
}

fn success(outcome: Outcome, now: chrono::DateTime<chrono::FixedOffset>) -> Response {
    let mut builder = Response::builder().status(StatusCode::OK);
    let body = match outcome {
        Outcome::Generated { feed, detected } => {
            builder = builder.header(header::CONTENT_TYPE, RSS_CONTENT_TYPE);
            if let Some(first) = detected.first() {
                for (name, value) in [
                    ("x-existing-feed-url", first.url.clone()),
                    ("x-existing-feed-title", encode_title(&first.title)),
                    ("x-existing-feed-type", first.kind.label().to_string()),
                ] {
                    if let Ok(value) = HeaderValue::from_str(&value) {
                        builder = builder.header(name, value);
                    }
                }
            }
            Body::from(feed.to_xml(now))
        }
        Outcome::Proxied {
            body, content_type, ..
        } => {
            let value = HeaderValue::from_str(&content_type)
                .unwrap_or(HeaderValue::from_static("application/xml"));
            builder = builder.header(header::CONTENT_TYPE, value);
            Body::from(body)
        }
    };
    builder
        .body(body)
        .unwrap_or_else(|_| error(StatusCode::INTERNAL_SERVER_ERROR, "Internal server error"))
}
