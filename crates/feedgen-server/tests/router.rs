//! Router (docs/specs/api.md A-1〜A-7)。通信せず、偽の `FeedService` を差し込む。

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use axum::Router;
use axum::body::Body;
use axum::http::{Method, Request, Response, StatusCode};
use chrono::{DateTime, FixedOffset};
use feedgen_core::detector::{FeedInfo, FeedKind};
use feedgen_core::generator::{GenerateOptions, Outcome};
use feedgen_core::models::{RssFeed, RssItem};
use feedgen_core::{FeedError, Result};
use feedgen_server::{AppConfig, FeedService, router};
use http_body_util::BodyExt;
use tokio::sync::{Notify, Semaphore};
use tower::ServiceExt;

type Factory = Box<dyn Fn() -> Result<Outcome> + Send + Sync>;

/// `gate` があるとき、`generate` は開始を `started` で知らせ、`gate` に許可が足されるまで待つ
/// (時間ではなく合図で順序を決めるため、テストが実行環境の速さに左右されない)。
struct Fake {
    factory: Factory,
    gate: Option<Semaphore>,
    started: Notify,
    /// `generate` が最後まで走らずに捨てられた (中断された) 回数。
    abandoned: AtomicUsize,
    seen: Mutex<Vec<(String, GenerateOptions)>>,
}

impl Fake {
    fn new(factory: impl Fn() -> Result<Outcome> + Send + Sync + 'static) -> Arc<Self> {
        Self::build(None, factory)
    }

    /// 許可を足すまで止まる。
    fn gated() -> Arc<Self> {
        Self::build(Some(Semaphore::new(0)), || generated(vec![]))
    }

    fn build(
        gate: Option<Semaphore>,
        factory: impl Fn() -> Result<Outcome> + Send + Sync + 'static,
    ) -> Arc<Self> {
        Arc::new(Self {
            factory: Box::new(factory),
            gate,
            started: Notify::new(),
            abandoned: AtomicUsize::new(0),
            seen: Mutex::new(Vec::new()),
        })
    }

    fn release(&self, count: usize) {
        self.gate.as_ref().unwrap().add_permits(count);
    }
}

struct AbandonGuard<'a> {
    counter: &'a AtomicUsize,
    finished: bool,
}

impl Drop for AbandonGuard<'_> {
    fn drop(&mut self) {
        if !self.finished {
            self.counter.fetch_add(1, Ordering::SeqCst);
        }
    }
}

impl FeedService for Fake {
    async fn generate(
        &self,
        url: &str,
        options: &GenerateOptions,
        _now: DateTime<FixedOffset>,
    ) -> Result<Outcome> {
        self.seen
            .lock()
            .unwrap()
            .push((url.to_string(), options.clone()));
        let mut guard = AbandonGuard {
            counter: &self.abandoned,
            finished: false,
        };
        self.started.notify_one();
        if let Some(gate) = &self.gate {
            gate.acquire().await.unwrap().forget();
        }
        guard.finished = true;
        (self.factory)()
    }
}

fn generated(detected: Vec<FeedInfo>) -> Result<Outcome> {
    Ok(Outcome::Generated {
        feed: RssFeed {
            title: "テスト".to_string(),
            description: "d".to_string(),
            link: "https://example.com/".to_string(),
            items: vec![RssItem {
                title: "t".to_string(),
                description: "x".to_string(),
                link: "https://example.com/1".to_string(),
                pub_date: None,
                guid: Some("g1".to_string()),
            }],
        },
        detected,
    })
}

fn info(title: &str) -> FeedInfo {
    FeedInfo {
        url: "https://example.com/feed.xml".to_string(),
        title: title.to_string(),
        kind: FeedKind::Atom,
    }
}

fn app(service: Arc<Fake>) -> Router {
    router(service, AppConfig::default())
}

async fn send(app: Router, method: Method, uri: &str) -> Response<Body> {
    app.oneshot(
        Request::builder()
            .method(method)
            .uri(uri)
            .header("origin", "https://reader.example")
            .body(Body::empty())
            .unwrap(),
    )
    .await
    .unwrap()
}

async fn get(app: Router, uri: &str) -> Response<Body> {
    send(app, Method::GET, uri).await
}

async fn body_bytes(response: Response<Body>) -> Vec<u8> {
    response
        .into_body()
        .collect()
        .await
        .unwrap()
        .to_bytes()
        .to_vec()
}

async fn body_json(response: Response<Body>) -> serde_json::Value {
    serde_json::from_slice(&body_bytes(response).await).unwrap()
}

fn header<'a>(response: &'a Response<Body>, name: &str) -> Option<&'a str> {
    response.headers().get(name).map(|v| v.to_str().unwrap())
}

#[tokio::test]
async fn health() {
    let response = get(app(Fake::new(|| generated(vec![]))), "/health").await;
    assert_eq!(response.status(), StatusCode::OK);
    let json = body_json(response).await;
    assert_eq!(json["status"], "healthy");
    assert_eq!(json["service"], "feedgen API");
}

#[tokio::test]
async fn root_describes_the_service() {
    let response = get(app(Fake::new(|| generated(vec![]))), "/").await;
    assert_eq!(response.status(), StatusCode::OK);
    let text = String::from_utf8(body_bytes(response).await).unwrap();
    assert!(text.contains("/feed") && text.contains("/health"), "{text}");
}

#[tokio::test]
async fn unknown_path_is_404_and_wrong_method_is_405_with_detail() {
    let service = Fake::new(|| generated(vec![]));
    let response = get(app(service.clone()), "/nope").await;
    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    assert!(body_json(response).await["detail"].is_string());

    let response = send(app(service), Method::POST, "/feed?url=https://e.com/").await;
    assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
    assert!(body_json(response).await["detail"].is_string());
}

#[tokio::test]
async fn cors_allows_any_origin_for_get_only() {
    let response = get(
        app(Fake::new(|| generated(vec![]))),
        "/feed?url=https://example.com/",
    )
    .await;
    assert_eq!(header(&response, "access-control-allow-origin"), Some("*"));
    assert!(header(&response, "access-control-allow-credentials").is_none());

    let preflight = app(Fake::new(|| generated(vec![])))
        .oneshot(
            Request::builder()
                .method(Method::OPTIONS)
                .uri("/feed")
                .header("origin", "https://reader.example")
                .header("access-control-request-method", "GET")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert!(preflight.status().is_success());
    let methods = header(&preflight, "access-control-allow-methods").unwrap();
    assert!(
        methods.contains("GET") && !methods.contains("POST"),
        "{methods}"
    );
}

#[tokio::test]
async fn generated_feed_is_rss_with_utf8_content_type() {
    let response = get(
        app(Fake::new(|| generated(vec![]))),
        "/feed?url=https://example.com/",
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        header(&response, "content-type"),
        Some("application/rss+xml; charset=utf-8")
    );
    assert!(header(&response, "x-existing-feed-url").is_none());
    let text = String::from_utf8(body_bytes(response).await).unwrap();
    assert!(text.contains("<rss") && text.contains("テスト") && text.contains("g1"));
}

#[tokio::test]
async fn proxied_body_and_content_type_pass_through_untouched() {
    let raw = vec![0xff, 0xfe, b'<', b'r', b's', b's', b'>'];
    let body = raw.clone();
    let service = Fake::new(move || {
        Ok(Outcome::Proxied {
            body: body.clone(),
            content_type: "application/atom+xml; charset=euc-jp".to_string(),
            source_url: "https://example.com/feed".to_string(),
        })
    });
    let response = get(app(service), "/feed?url=https://example.com/").await;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        header(&response, "content-type"),
        Some("application/atom+xml; charset=euc-jp")
    );
    assert_eq!(body_bytes(response).await, raw);
}

#[tokio::test]
async fn feed_first_detection_headers_with_japanese_title_encoded() {
    let service = Fake::new(|| generated(vec![info("新着\r\nニュース"), info("second")]));
    let response = get(
        app(service),
        "/feed?url=https://example.com/&feed_first=true",
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        header(&response, "x-existing-feed-url"),
        Some("https://example.com/feed.xml")
    );
    assert_eq!(header(&response, "x-existing-feed-type"), Some("Atom"));
    assert_eq!(
        header(&response, "x-existing-feed-title"),
        Some("%E6%96%B0%E7%9D%80%E3%83%8B%E3%83%A5%E3%83%BC%E3%82%B9")
    );
}

#[tokio::test]
async fn long_detected_title_is_truncated_not_fatal() {
    let service = Fake::new(|| generated(vec![info(&"x".repeat(5000))]));
    let response = get(
        app(service),
        "/feed?url=https://example.com/&feed_first=true",
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        header(&response, "x-existing-feed-title").unwrap().len(),
        200
    );
}

#[tokio::test]
async fn feed_first_without_candidates_has_no_headers() {
    let response = get(
        app(Fake::new(|| generated(vec![]))),
        "/feed?url=https://example.com/&feed_first=true",
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    assert!(header(&response, "x-existing-feed-url").is_none());
    assert!(header(&response, "x-existing-feed-type").is_none());
    assert!(header(&response, "x-existing-feed-title").is_none());
}

#[tokio::test]
async fn parameters_reach_the_service() {
    let service = Fake::new(|| generated(vec![]));
    let uri = "/feed?url=https%3A%2F%2Fexample.com%2Fa%3Fb%3D1&max_items=5&use_feed=true&feed_first=true&user_agent=ua%2F9";
    get(app(service.clone()), uri).await;
    let seen = service.seen.lock().unwrap();
    assert_eq!(seen.len(), 1);
    assert_eq!(seen[0].0, "https://example.com/a?b=1");
    assert_eq!(seen[0].1.max_items, 5);
    assert!(seen[0].1.use_feed && seen[0].1.feed_first);
    assert_eq!(seen[0].1.user_agent, "ua/9");
}

#[tokio::test]
async fn default_user_agent_is_feedgen_api() {
    let service = Fake::new(|| generated(vec![]));
    get(app(service.clone()), "/feed?url=https://example.com/").await;
    assert_eq!(
        service.seen.lock().unwrap()[0].1.user_agent,
        "feedgen-api/1.0"
    );
}

#[tokio::test]
async fn validation_errors_never_reach_the_service() {
    let service = Fake::new(|| generated(vec![]));
    let cases = [
        ("/feed", StatusCode::UNPROCESSABLE_ENTITY),
        (
            "/feed?url=https://e.com/&max_items=0",
            StatusCode::UNPROCESSABLE_ENTITY,
        ),
        (
            "/feed?url=https://e.com/&use_feed=maybe",
            StatusCode::UNPROCESSABLE_ENTITY,
        ),
        (
            "/feed?url=https://e.com/&translate=true",
            StatusCode::BAD_REQUEST,
        ),
        (
            "/feed?url=https://e.com/&decode_google_news=true",
            StatusCode::BAD_REQUEST,
        ),
        (
            "/feed?url=https://e.com/&user_agent=%E6%97%A5",
            StatusCode::BAD_REQUEST,
        ),
    ];
    for (uri, status) in cases {
        let response = get(app(service.clone()), uri).await;
        assert_eq!(response.status(), status, "{uri}");
        assert!(body_json(response).await["detail"].is_string(), "{uri}");
    }
    assert!(service.seen.lock().unwrap().is_empty());
}

#[tokio::test]
async fn core_errors_map_to_400_with_the_core_message() {
    let service = Fake::new(|| Err(FeedError::UnsafeUrl("取得できない URL です".to_string())));
    let response = get(app(service), "/feed?url=http://127.0.0.1/").await;
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert_eq!(body_json(response).await["detail"], "取得できない URL です");

    let service = Fake::new(|| Err(FeedError::Http("HTTP取得エラー: boom".to_string())));
    let response = get(app(service), "/feed?url=https://example.com/").await;
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert!(
        body_json(response).await["detail"]
            .as_str()
            .unwrap()
            .contains("boom")
    );
}

#[tokio::test]
async fn panic_becomes_generic_500_without_details() {
    let service = Fake::new(|| panic!("secret internal detail"));
    let response = get(app(service), "/feed?url=https://example.com/").await;
    assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);
    let json = body_json(response).await;
    assert_eq!(json["detail"], "Internal server error");
}

const WAIT: Duration = Duration::from_secs(5);

fn config(timeout: Duration, max_concurrent: usize) -> AppConfig {
    AppConfig {
        timeout,
        max_concurrent,
    }
}

/// 上限に空きができる (503 でなくなる) まで、短い間隔で再試行する。最後の応答を返す。
async fn until_not_503(app: &Router, uri: &str) -> Response<Body> {
    tokio::time::timeout(WAIT, async {
        loop {
            let response = get(app.clone(), uri).await;
            if response.status() != StatusCode::SERVICE_UNAVAILABLE {
                return response;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .expect("枠が戻らなかった")
}

#[tokio::test]
async fn stalled_generation_times_out_with_504() {
    let service = Fake::gated();
    let app = router(service, config(Duration::from_millis(50), 4));
    let response = tokio::time::timeout(WAIT, get(app, "/feed?url=https://example.com/"))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::GATEWAY_TIMEOUT);
    assert!(body_json(response).await["detail"].is_string());
}

#[tokio::test]
async fn over_limit_gets_503_and_slot_is_released_afterwards() {
    let service = Fake::gated();
    let app = router(service.clone(), config(Duration::from_secs(60), 1));
    let first = tokio::spawn(get(app.clone(), "/feed?url=https://example.com/"));
    service.started.notified().await;

    let rejected = tokio::time::timeout(WAIT, get(app.clone(), "/feed?url=https://example.com/"))
        .await
        .expect("待たずに返る");
    assert_eq!(rejected.status(), StatusCode::SERVICE_UNAVAILABLE);
    assert!(body_json(rejected).await["detail"].is_string());
    // 上限の対象は /feed だけ。
    assert_eq!(get(app.clone(), "/health").await.status(), StatusCode::OK);

    service.release(2);
    assert_eq!(first.await.unwrap().status(), StatusCode::OK);
    let after = until_not_503(&app, "/feed?url=https://example.com/").await;
    assert_eq!(after.status(), StatusCode::OK);
}

#[tokio::test]
async fn slot_is_released_after_timeout() {
    let service = Fake::gated();
    let app = router(service, config(Duration::from_millis(50), 1));
    let first = tokio::time::timeout(WAIT, get(app.clone(), "/feed?url=https://example.com/"))
        .await
        .unwrap();
    assert_eq!(first.status(), StatusCode::GATEWAY_TIMEOUT);
    let second = until_not_503(&app, "/feed?url=https://example.com/").await;
    assert_eq!(
        second.status(),
        StatusCode::GATEWAY_TIMEOUT,
        "503 ではなく再び処理される"
    );
}

#[tokio::test]
async fn disconnect_keeps_the_slot_until_generation_finishes() {
    let service = Fake::gated();
    let app = router(service.clone(), config(Duration::from_secs(60), 1));
    let client = tokio::spawn(get(app.clone(), "/feed?url=https://example.com/"));
    service.started.notified().await;

    // クライアントの切断 = 応答の future が捨てられる。
    client.abort();
    let _ = client.await;

    let rejected = get(app.clone(), "/feed?url=https://example.com/").await;
    assert_eq!(
        rejected.status(),
        StatusCode::SERVICE_UNAVAILABLE,
        "処理が続いている間は、枠を返さない"
    );

    service.release(2);
    let after = until_not_503(&app, "/feed?url=https://example.com/").await;
    assert_eq!(after.status(), StatusCode::OK);
}

#[tokio::test]
async fn disconnect_does_not_escape_the_deadline() {
    let service = Fake::gated();
    let app = router(service.clone(), config(Duration::from_millis(100), 1));
    let client = tokio::spawn(get(app.clone(), "/feed?url=https://example.com/"));
    service.started.notified().await;
    client.abort();
    let _ = client.await;

    // 切断後も、処理そのものが締切で打ち切られる (止まったままの処理が残り続けない)。
    tokio::time::timeout(WAIT, async {
        while service.abandoned.load(Ordering::SeqCst) == 0 {
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .expect("締切で処理が打ち切られなかった");
    // 枠も戻っている。
    let after = until_not_503(&app, "/feed?url=https://example.com/").await;
    assert_eq!(after.status(), StatusCode::GATEWAY_TIMEOUT);
}

#[tokio::test]
async fn unrepresentable_header_value_drops_only_that_header() {
    let service = Fake::new(|| {
        generated(vec![FeedInfo {
            url: "https://example.com/\nfeed".to_string(),
            title: "ok".to_string(),
            kind: FeedKind::Rss,
        }])
    });
    let response = get(
        app(service),
        "/feed?url=https://example.com/&feed_first=true",
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    assert!(header(&response, "x-existing-feed-url").is_none());
    assert_eq!(header(&response, "x-existing-feed-title"), Some("ok"));
    assert_eq!(header(&response, "x-existing-feed-type"), Some("RSS"));
}

#[tokio::test]
async fn invalid_proxied_content_type_falls_back_to_xml() {
    let service = Fake::new(|| {
        Ok(Outcome::Proxied {
            body: b"<rss/>".to_vec(),
            content_type: "application/rss+xml\nX-Injected: 1".to_string(),
            source_url: "https://example.com/feed".to_string(),
        })
    });
    let response = get(app(service), "/feed?url=https://example.com/").await;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(header(&response, "content-type"), Some("application/xml"));
    assert!(header(&response, "x-injected").is_none());
}

#[tokio::test]
async fn undecodable_query_bytes_become_replacement_characters() {
    // 不正な UTF-8 は置換文字になり、URL の可否は、取得層 (コア) が決める。
    let service = Fake::new(|| generated(vec![]));
    let response = get(app(service.clone()), "/feed?url=%FF%FE").await;
    assert_eq!(response.status(), StatusCode::OK);
    let seen = service.seen.lock().unwrap();
    assert!(seen[0].0.contains('\u{FFFD}'), "{:?}", seen[0].0);
}
