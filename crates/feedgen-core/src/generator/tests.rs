//! docs/specs/pipeline.md 7 章のテスト (RED)。ローカルのサイト用サーバー 1 台で、関心ごとにまとめる。

use chrono::{DateTime, FixedOffset, TimeZone};

use super::*;
use crate::detector::FeedKind;
use crate::detector::probe_server::{
    self, LocalLookup, ProbeServer, Route, lenient_fetcher, refusing_fetcher, site_url,
};
use crate::error::FeedError;

// ---- 共通の道具 ----

const UA: &str = "test-agent/1.0";

fn now() -> DateTime<FixedOffset> {
    FixedOffset::east_opt(0)
        .expect("オフセットが不正")
        .with_ymd_and_hms(2026, 11, 3, 0, 0, 0)
        .single()
        .expect("日時が不正")
}

fn options(use_feed: bool, feed_first: bool) -> GenerateOptions {
    GenerateOptions {
        user_agent: UA.to_string(),
        use_feed,
        feed_first,
        ..GenerateOptions::default()
    }
}

fn generator() -> FeedGenerator<LocalLookup> {
    FeedGenerator::with_fetcher(lenient_fetcher())
}

const PAGE: &str = r#"<html><head><title>Site</title><meta name="description" content="Desc"></head><body>
<h2><a href="/e/1">First entry</a></h2><p>Summary one.</p>
<h2><a href="/e/2">Second entry</a></h2><p>Summary two.</p>
<h2><a href="/e/3">Third entry</a></h2><p>Summary three.</p>
</body></html>"#;

const PAGE_WITH_LINKS: &str = r#"<html><head><title>Site</title><meta name="description" content="Desc">
<link rel="alternate" type="application/rss+xml" title="RSS" href="/feed.xml">
<link rel="alternate" type="application/atom+xml" title="Atom" href="/atom.xml">
</head><body>
<h2><a href="/e/1">First entry</a></h2><p>Summary one.</p>
</body></html>"#;

const RSS2: &str =
    r#"<?xml version="1.0"?><rss version="2.0"><channel><title>T</title></channel></rss>"#;
const RDF: &str = r#"<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><channel><title>T</title></channel></rdf:RDF>"#;
const ATOM: &str =
    r#"<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>T</title></feed>"#;

fn generated(outcome: Outcome) -> (RssFeed, Vec<FeedInfo>) {
    match outcome {
        Outcome::Generated { feed, detected } => (feed, detected),
        other => panic!("Generated のはずが {other:?}"),
    }
}

fn proxied(outcome: Outcome) -> (Vec<u8>, String, String) {
    match outcome {
        Outcome::Proxied {
            body,
            content_type,
            source_url,
        } => (body, content_type, source_url),
        other => panic!("Proxied のはずが {other:?}"),
    }
}

async fn run(
    server: &ProbeServer,
    path: &str,
    options: &GenerateOptions,
) -> crate::error::Result<Outcome> {
    generator()
        .generate(&site_url(server, path), options, now())
        .await
}

fn gets(server: &ProbeServer) -> Vec<String> {
    server
        .requests()
        .into_iter()
        .filter(|(method, _)| method == "GET")
        .map(|(_, path)| path)
        .collect()
}

fn heads(server: &ProbeServer) -> usize {
    server
        .requests()
        .iter()
        .filter(|(method, _)| method == "HEAD")
        .count()
}

// ---- G-1、G-2: 取得は 1 回、フィールド ----

#[tokio::test]
async fn a_plain_page_is_fetched_once_and_turned_into_a_feed() {
    let server = probe_server::spawn(vec![Route::page("/", "text/html", PAGE)]).await;
    let url = site_url(&server, "/");

    let (feed, detected) = generated(run(&server, "/", &options(false, false)).await.unwrap());

    assert_eq!(feed.title, "Site");
    assert_eq!(feed.description, "Desc");
    assert_eq!(feed.link, url, "チャンネルの link は渡した URL");
    let titles: Vec<&str> = feed.items.iter().map(|i| i.title.as_str()).collect();
    assert_eq!(titles, ["First entry", "Second entry", "Third entry"]);
    assert_eq!(
        feed.items[0].guid.as_deref(),
        Some(format!("{url}#heading-0").as_str()),
        "guid は渡した URL から作る"
    );
    assert!(feed.items.iter().all(|i| i.pub_date == Some(now())));
    assert!(detected.is_empty());
    // 取得は対象の GET 1 回だけ。検出の通信はしない。
    assert_eq!(server.requests(), [("GET".to_string(), "/".to_string())]);
}

#[tokio::test]
async fn max_items_reaches_the_parser() {
    let server = probe_server::spawn(vec![Route::page("/", "text/html", PAGE)]).await;
    let mut opts = options(false, false);
    opts.max_items = 2;

    let (feed, _) = generated(run(&server, "/", &opts).await.unwrap());
    assert_eq!(feed.items.len(), 2);
}

// ---- G-7: URL 自体がフィード ----

#[tokio::test]
async fn a_url_that_is_itself_a_feed_is_proxied_whatever_the_flags() {
    let cases = [
        (RSS2, "application/rss+xml; charset=UTF-8"),
        (RDF, "application/rss+xml; charset=UTF-8"),
        (ATOM, "application/atom+xml; charset=UTF-8"),
    ];
    for (body, expected_type) in cases {
        for (use_feed, feed_first) in [(false, false), (true, false), (false, true), (true, true)] {
            let server = probe_server::spawn(vec![Route::page(
                "/f",
                "application/xml; charset=UTF-8",
                body,
            )])
            .await;

            let outcome = run(&server, "/f", &options(use_feed, feed_first))
                .await
                .unwrap();
            let (got_body, content_type, source_url) = proxied(outcome);

            let label = format!("use_feed={use_feed} feed_first={feed_first}");
            assert_eq!(got_body, body.as_bytes(), "{label}: 本文はバイト列のまま");
            assert_eq!(content_type, expected_type, "{label}");
            assert_eq!(source_url, site_url(&server, "/f"), "{label}");
            assert_eq!(server.requests().len(), 1, "{label}: 取得は 1 回だけ");
        }
    }
}

#[tokio::test]
async fn xhtml_pages_are_not_mistaken_for_feeds() {
    // Content-Type に xml を含んでも、ルート要素が html なら、フィードではない
    let xhtml = r#"<?xml version="1.0"?><!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>X</title></head><body>
<h2><a href="/e/1">XHTML entry</a></h2></body></html>"#;
    let server = probe_server::spawn(vec![Route::page("/", "application/xhtml+xml", xhtml)]).await;

    let (feed, _) = generated(run(&server, "/", &options(true, false)).await.unwrap());
    assert_eq!(feed.items[0].title, "XHTML entry");
}

// ---- G-8、G-11: ステータス ----

#[tokio::test]
async fn statuses_other_than_200_are_errors_with_the_status_in_the_message() {
    for status in [404u16, 202, 500, 204] {
        let server = probe_server::spawn(vec![Route::new("/", status, "text/html")]).await;

        let err = run(&server, "/", &options(false, false)).await.unwrap_err();
        let expected = format!("取得先が内容を返しませんでした (HTTP {status})");
        assert!(
            matches!(&err, FeedError::Http(m) if *m == expected),
            "{status}: {err:?}"
        );
    }
}

#[tokio::test]
async fn an_empty_200_body_is_an_empty_feed_not_an_error() {
    let server = probe_server::spawn(vec![Route::page("/", "text/html", "")]).await;

    let (feed, _) = generated(run(&server, "/", &options(false, false)).await.unwrap());
    assert!(feed.items.is_empty());
    assert_eq!(feed.title, "無題");
}

// ---- G-2: 検出と代理取得 ----

#[tokio::test]
async fn use_feed_proxies_the_feed_announced_in_the_page() {
    let server = probe_server::spawn(vec![
        Route::page("/", "text/html", PAGE_WITH_LINKS),
        Route::page("/feed.xml", "application/rss+xml", RSS2),
        Route::page("/atom.xml", "application/atom+xml", ATOM),
    ])
    .await;

    let outcome = run(&server, "/", &options(true, false)).await.unwrap();
    let (body, content_type, source_url) = proxied(outcome);

    assert_eq!(body, RSS2.as_bytes(), "先頭のフィードが使われる");
    assert_eq!(content_type, "application/rss+xml");
    assert_eq!(source_url, site_url(&server, "/feed.xml"));
    // 共通パスの確認 (HEAD) はしない。対象と、フィードの GET だけ。
    assert_eq!(
        server.requests(),
        [
            ("GET".to_string(), "/".to_string()),
            ("GET".to_string(), "/feed.xml".to_string())
        ]
    );
}

#[tokio::test]
async fn use_feed_probes_common_paths_when_the_page_announces_nothing() {
    let server = probe_server::spawn(vec![
        Route::page("/", "text/html", PAGE),
        Route::page("/rss", "application/rss+xml", RSS2),
    ])
    .await;

    let outcome = run(&server, "/", &options(true, false)).await.unwrap();
    let (body, _, source_url) = proxied(outcome);

    assert_eq!(body, RSS2.as_bytes());
    assert_eq!(source_url, site_url(&server, "/rss"));
    assert_eq!(heads(&server), 8, "共通パスを HEAD で確かめる");
    let mut get_paths = gets(&server);
    get_paths.sort();
    assert_eq!(get_paths, ["/", "/rss"]);
}

#[tokio::test]
async fn an_unusable_detected_feed_falls_back_to_the_html_without_an_error() {
    let cases: [(&str, Route); 3] = [
        (
            "取得先が 404",
            Route::new("/feed.xml", 404, "application/rss+xml"),
        ),
        (
            "200 だが本文が HTML",
            Route::page(
                "/feed.xml",
                "application/rss+xml",
                "<html><body>not a feed</body></html>",
            ),
        ),
        (
            "202 (200 だけが成功)",
            Route::new("/feed.xml", 202, "application/rss+xml"),
        ),
    ];
    for (label, feed_route) in cases {
        let server = probe_server::spawn(vec![
            Route::page("/", "text/html", PAGE_WITH_LINKS),
            feed_route,
        ])
        .await;

        let outcome = run(&server, "/", &options(true, false)).await.unwrap();
        let (feed, _) = generated(outcome);
        assert_eq!(feed.items[0].title, "First entry", "{label}");
    }
}

#[tokio::test]
async fn feed_first_reports_candidates_without_proxying() {
    let server = probe_server::spawn(vec![
        Route::page("/", "text/html", PAGE_WITH_LINKS),
        Route::page("/feed.xml", "application/rss+xml", RSS2),
    ])
    .await;

    let (feed, detected) = generated(run(&server, "/", &options(false, true)).await.unwrap());

    assert_eq!(feed.items[0].title, "First entry");
    let found: Vec<(String, &str, &str)> = detected
        .iter()
        .map(|f| (f.url.clone(), f.title.as_str(), f.kind.label()))
        .collect();
    assert_eq!(
        found,
        [
            (site_url(&server, "/feed.xml"), "RSS", "RSS"),
            (site_url(&server, "/atom.xml"), "Atom", "Atom"),
        ]
    );
    assert_eq!(detected[0].kind, FeedKind::Rss);
    assert_eq!(gets(&server), ["/"], "フィードは取得しない");
}

#[tokio::test]
async fn use_feed_takes_priority_over_feed_first() {
    let server = probe_server::spawn(vec![
        Route::page("/", "text/html", PAGE_WITH_LINKS),
        Route::page("/feed.xml", "application/rss+xml", RSS2),
    ])
    .await;

    let outcome = run(&server, "/", &options(true, true)).await.unwrap();
    let (body, _, _) = proxied(outcome);
    assert_eq!(body, RSS2.as_bytes());
}

#[tokio::test]
async fn nothing_is_detected_without_the_flags() {
    let server = probe_server::spawn(vec![Route::page("/", "text/html", PAGE_WITH_LINKS)]).await;

    let (_, detected) = generated(run(&server, "/", &options(false, false)).await.unwrap());

    assert!(detected.is_empty());
    assert_eq!(server.requests().len(), 1, "検出の通信をしない");
}

// ---- G-2: 基準 URL ----

#[tokio::test]
async fn guids_use_the_given_url_and_detection_uses_the_final_url() {
    let page = r#"<html><head><title>New</title>
<link rel="alternate" type="application/rss+xml" href="rel-feed.xml"></head><body>
<h2><a href="/e/1">Entry</a></h2></body></html>"#;
    let routes = || {
        vec![
            Route::redirect("/old", "/dir/new"),
            Route::page("/dir/new", "text/html", page),
            Route::page("/dir/rel-feed.xml", "application/rss+xml", RSS2),
        ]
    };

    // 解析: guid とチャンネルの link は、渡した URL (リダイレクト前) から作る
    let server = probe_server::spawn(routes()).await;
    let (feed, _) = generated(run(&server, "/old", &options(false, false)).await.unwrap());
    let original = site_url(&server, "/old");
    assert_eq!(feed.link, original);
    assert_eq!(
        feed.items[0].guid.as_deref(),
        Some(format!("{original}#heading-0").as_str())
    );

    // 検出: 相対の href は、最終 URL (/dir/new) に対して解決される
    let server = probe_server::spawn(routes()).await;
    let outcome = run(&server, "/old", &options(true, false)).await.unwrap();
    let (_, _, source_url) = proxied(outcome);
    assert_eq!(source_url, site_url(&server, "/dir/rel-feed.xml"));
}

// ---- G-10: User-Agent ----

#[tokio::test]
async fn the_user_agent_is_sent_on_every_request() {
    // 検出で共通パスの確認 (HEAD 8 本) まで行い、見つからずに HTML の解析に進むケース
    let server = probe_server::spawn(vec![Route::page("/", "text/html", PAGE)]).await;
    let mut opts = options(true, false);
    opts.user_agent = "my-agent/2.0".to_string();

    let _ = run(&server, "/", &opts).await.unwrap();

    let agents = server.user_agents();
    assert_eq!(agents.len(), 9, "対象の GET 1 回 + HEAD 8 本");
    assert!(agents.iter().all(|ua| ua == "my-agent/2.0"), "{agents:?}");

    // 検出したフィードの取得にも付く
    let server = probe_server::spawn(vec![
        Route::page("/", "text/html", PAGE_WITH_LINKS),
        Route::page("/feed.xml", "application/rss+xml", RSS2),
    ])
    .await;
    let _ = run(&server, "/", &opts).await.unwrap();
    let agents = server.user_agents();
    assert_eq!(agents.len(), 2);
    assert!(agents.iter().all(|ua| ua == "my-agent/2.0"), "{agents:?}");
}

// ---- G-9: 文字コード ----

/// 「日本語」の Shift_JIS のバイト列を、見出しに入れたページ。
fn sjis_page(head_extra: &str) -> Vec<u8> {
    let mut page =
        format!("<html><head><title>T</title>{head_extra}</head><body><h2><a href=\"/e\">")
            .into_bytes();
    page.extend_from_slice(&[0x93, 0xFA, 0x96, 0x7B, 0x8C, 0xEA]);
    page.extend_from_slice(b"</a></h2></body></html>");
    page
}

#[tokio::test]
async fn shift_jis_pages_are_decoded_from_the_header_or_the_meta() {
    // Content-Type の charset
    let server = probe_server::spawn(vec![Route::page(
        "/",
        "text/html; charset=Shift_JIS",
        sjis_page(""),
    )])
    .await;
    let (feed, _) = generated(run(&server, "/", &options(false, false)).await.unwrap());
    assert_eq!(feed.items[0].title, "日本語");

    // charset のない Content-Type と、<meta charset>
    let server = probe_server::spawn(vec![Route::page(
        "/",
        "text/html",
        sjis_page(r#"<meta charset="Shift_JIS">"#),
    )])
    .await;
    let (feed, _) = generated(run(&server, "/", &options(false, false)).await.unwrap());
    assert_eq!(feed.items[0].title, "日本語");
}

// ---- G-3: 取得層の拒否 ----

#[tokio::test]
async fn refused_and_invalid_urls_are_unsafe_url_errors_and_never_connect() {
    let server = probe_server::spawn(vec![Route::page("/", "text/html", PAGE)]).await;
    let generator = FeedGenerator::with_fetcher(refusing_fetcher());

    let refused = generator
        .generate(&site_url(&server, "/"), &options(false, false), now())
        .await;
    assert!(
        matches!(refused, Err(FeedError::UnsafeUrl(_))),
        "{refused:?}"
    );

    for url in [
        "not a url",
        "",
        "ftp://example.com/",
        "http://127.0.0.1\\@8.8.8.8/",
    ] {
        let result = generator.generate(url, &options(false, false), now()).await;
        assert!(
            matches!(result, Err(FeedError::UnsafeUrl(_))),
            "{url:?}: {result:?}"
        );
    }
    assert!(
        server.requests().is_empty(),
        "拒否した相手に接続してはいけない"
    );
}

// ---- 本番の入口 (実際の名前解決) ----

#[tokio::test]
async fn production_generator_refuses_localhost_via_real_resolution() {
    // 本番用の FeedGenerator::new() は、許可アドレスを持たず、localhost (ループバック) を拒否する。
    // 名前解決は localhost だけを使う (外部ネットワークに依存しない)。
    let result = FeedGenerator::new()
        .generate("http://localhost/", &GenerateOptions::default(), now())
        .await;
    assert!(matches!(result, Err(FeedError::UnsafeUrl(_))), "{result:?}");
}
