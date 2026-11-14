//! `GET /admin` (docs/specs/admin.md M-2、M-3)。通信せず、偽の `FeedService` を差し込む。

use std::sync::Arc;

use axum::Router;
use axum::body::Body;
use axum::http::{Method, Request, Response, StatusCode};
use chrono::{DateTime, FixedOffset};
use feedgen_core::Result;
use feedgen_core::generator::{GenerateOptions, Outcome};
use feedgen_core::models::RssFeed;
use feedgen_server::{AppConfig, FeedService, router};
use http_body_util::BodyExt;
use tower::ServiceExt;

struct Fake;

impl FeedService for Fake {
    async fn generate(
        &self,
        _url: &str,
        _options: &GenerateOptions,
        _now: DateTime<FixedOffset>,
    ) -> Result<Outcome> {
        Ok(Outcome::Generated {
            feed: RssFeed {
                title: "T".to_string(),
                description: "d".to_string(),
                link: "https://example.com/".to_string(),
                items: vec![],
            },
            detected: vec![],
        })
    }
}

const CSP: &str = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; \
connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";

fn app(admin: bool) -> Router {
    router(
        Arc::new(Fake),
        AppConfig {
            admin,
            ..AppConfig::default()
        },
    )
}

async fn send(app: Router, method: Method, uri: &str) -> Response<Body> {
    app.oneshot(
        Request::builder()
            .method(method)
            .uri(uri)
            .body(Body::empty())
            .unwrap(),
    )
    .await
    .unwrap()
}

async fn text(response: Response<Body>) -> String {
    String::from_utf8(
        response
            .into_body()
            .collect()
            .await
            .unwrap()
            .to_bytes()
            .to_vec(),
    )
    .unwrap()
}

fn header<'a>(response: &'a Response<Body>, name: &str) -> Option<&'a str> {
    response.headers().get(name).map(|v| v.to_str().unwrap())
}

// ---- 無効 (既定) ----

#[tokio::test]
async fn disabled_by_default_in_app_config() {
    assert!(!AppConfig::default().admin);
}

#[tokio::test]
async fn disabled_admin_is_404_with_detail_and_no_page() {
    let response = send(app(false), Method::GET, "/admin").await;
    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    assert_eq!(header(&response, "content-type"), Some("application/json"));
    let body = text(response).await;
    assert!(body.contains("\"detail\""), "{body}");
    assert!(!body.to_lowercase().contains("<html"), "{body}");
}

#[tokio::test]
async fn disabled_admin_variants_are_404() {
    for uri in ["/admin/", "/admin/x", "/admin?x=1"] {
        let response = send(app(false), Method::GET, uri).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND, "{uri}");
    }
}

// ---- 有効 ----

#[tokio::test]
async fn enabled_admin_serves_html() {
    let response = send(app(true), Method::GET, "/admin").await;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        header(&response, "content-type"),
        Some("text/html; charset=utf-8")
    );
    let body = text(response).await;
    assert!(body.to_lowercase().contains("<html"), "{body}");
    assert_eq!(
        body,
        feedgen_server::admin::PAGE,
        "埋め込んだ HTML そのもの"
    );
}

#[tokio::test]
async fn enabled_admin_has_security_headers() {
    let response = send(app(true), Method::GET, "/admin").await;
    assert_eq!(header(&response, "cache-control"), Some("no-store"));
    assert_eq!(header(&response, "x-content-type-options"), Some("nosniff"));
    assert_eq!(header(&response, "x-frame-options"), Some("DENY"));
    assert_eq!(header(&response, "referrer-policy"), Some("no-referrer"));
    assert_eq!(header(&response, "content-security-policy"), Some(CSP));
}

#[tokio::test]
async fn enabled_admin_sub_paths_are_404_and_other_methods_405() {
    for uri in ["/admin/", "/admin/x", "/admin/index.html"] {
        let response = send(app(true), Method::GET, uri).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND, "{uri}");
    }
    let response = send(app(true), Method::POST, "/admin").await;
    assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
}

#[tokio::test]
async fn security_headers_are_only_on_the_admin_page() {
    let response = send(app(true), Method::GET, "/health").await;
    assert_eq!(response.status(), StatusCode::OK);
    assert!(header(&response, "content-security-policy").is_none());
    assert!(header(&response, "x-frame-options").is_none());
}

// ---- 既存の挙動は、有効でも無効でも、変わらない ----

#[tokio::test]
async fn existing_endpoints_are_unaffected() {
    for admin in [false, true] {
        let health = send(app(admin), Method::GET, "/health").await;
        assert_eq!(health.status(), StatusCode::OK, "admin={admin}");
        let feed = send(app(admin), Method::GET, "/feed?url=https://example.com/").await;
        assert_eq!(feed.status(), StatusCode::OK, "admin={admin}");
        assert_eq!(
            header(&feed, "content-type"),
            Some("application/rss+xml; charset=utf-8")
        );
        let missing = send(app(admin), Method::GET, "/nope").await;
        assert_eq!(missing.status(), StatusCode::NOT_FOUND, "admin={admin}");
    }
}

#[tokio::test]
async fn root_json_does_not_advertise_admin() {
    for admin in [false, true] {
        let response = send(app(admin), Method::GET, "/").await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = text(response).await;
        assert!(!body.contains("/admin"), "admin={admin}: {body}");
    }
}
