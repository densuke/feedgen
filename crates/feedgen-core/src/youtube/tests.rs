//! docs/specs/youtube.md 5 章のテスト。API はローカルの偽サーバーに差し替える (実ネットワーク、実キーなし)。

use chrono::{DateTime, FixedOffset, TimeZone};

use super::*;
use crate::detector::probe_server::{self, LocalLookup, ProbeServer, Route, lenient_fetcher};
use crate::generator::{FeedGenerator, GenerateOptions, Outcome};

const KEY: &str = "fake-key&x=1";
const SEARCH: &str =
    "https://www.youtube.com/results?search_query=AI+%E9%96%8B%E7%99%BA&sp=CAESAA%253D%253D";

fn now() -> DateTime<FixedOffset> {
    FixedOffset::east_opt(0)
        .expect("オフセットが不正")
        .with_ymd_and_hms(2026, 11, 3, 0, 0, 0)
        .single()
        .expect("日時が不正")
}

// ---- Y-1: 対象 URL の判定 ----

#[test]
fn only_www_youtube_search_urls_are_targets() {
    let yes = [
        ("https://www.youtube.com/results?search_query=rust", "rust"),
        ("http://WWW.YouTube.com/results?search_query=a+b", "a b"),
        (SEARCH, "AI 開発"),
        (
            "https://www.youtube.com/results?search_query=first&search_query=second",
            "first",
        ),
    ];
    for (url, query) in yes {
        assert_eq!(search_query(url).as_deref(), Some(query), "{url}");
    }
    let no = [
        "https://m.youtube.com/results?search_query=rust",
        "https://youtube.com/results?search_query=rust",
        "https://www.youtube.com/watch?v=abc",
        "https://www.youtube.com/results",
        "https://www.youtube.com/results?search_query=",
        "https://www.youtube.com/results?search_query=+",
        "https://www.youtube.com:8443/results?search_query=rust",
        "ftp://www.youtube.com/results?search_query=rust",
        "https://www.youtube.com/@channel",
        "not a url",
    ];
    for url in no {
        assert_eq!(search_query(url), None, "{url}");
    }
}

// ---- Y-3: API の URL ----

#[test]
fn api_url_clamps_max_results_and_encodes_query_and_key() {
    let url = api_url("https://api.example/search", "a&b=c 開", 100, KEY);
    let parsed = url::Url::parse(&url).unwrap();
    let pairs: Vec<(String, String)> = parsed.query_pairs().into_owned().collect();
    let get = |name: &str| {
        pairs
            .iter()
            .find(|(k, _)| k == name)
            .map(|(_, v)| v.clone())
    };
    assert_eq!(get("part").as_deref(), Some("snippet"));
    assert_eq!(get("type").as_deref(), Some("video"));
    assert_eq!(get("order").as_deref(), Some("relevance"));
    assert_eq!(get("maxResults").as_deref(), Some("50"));
    assert_eq!(get("q").as_deref(), Some("a&b=c 開"));
    assert_eq!(get("key").as_deref(), Some(KEY));

    let low = api_url("https://api.example/search", "a", 0, KEY);
    assert!(low.contains("maxResults=1&"), "{low}");
}

// ---- Y-4、Y-5: 応答の解釈 ----

fn video(
    id: Option<&str>,
    title: Option<&str>,
    description: &str,
    channel: &str,
    at: &str,
) -> String {
    let id = id.map_or("{}".to_string(), |id| format!(r#"{{"videoId":"{id}"}}"#));
    let title = title.map_or(String::new(), |t| format!(r#""title":"{t}","#));
    format!(
        r#"{{"id":{id},"snippet":{{{title}"description":"{description}","channelTitle":"{channel}","publishedAt":"{at}"}}}}"#
    )
}

fn body(items: &[String]) -> Vec<u8> {
    format!(r#"{{"items":[{}]}}"#, items.join(",")).into_bytes()
}

#[test]
fn items_become_articles_in_api_order() {
    let json = body(&[
        video(
            Some("v1"),
            Some("Tom &amp; Jerry&#39;s &quot;show&quot;"),
            "desc",
            "Chan",
            "2026-11-01T10:00:00Z",
        ),
        video(None, Some("skipped"), "", "", ""),
        video(Some("v2"), None, "", "", "broken"),
    ]);
    let feed = feed_from_response(200, &json, "AI 開発", SEARCH, 20, now()).unwrap();

    assert_eq!(feed.title, "YouTube検索: AI 開発");
    assert_eq!(feed.description, "YouTube検索「AI 開発」の結果");
    assert_eq!(feed.link, SEARCH, "link は入力の URL そのまま");
    assert_eq!(feed.items.len(), 2, "videoId のないものは飛ばす");

    let first = &feed.items[0];
    assert_eq!(first.title, r#"Tom & Jerry's "show""#, "文字参照を復号する");
    assert_eq!(first.link, "https://www.youtube.com/watch?v=v1");
    assert_eq!(first.guid.as_deref(), Some("youtube-video-v1"));
    assert_eq!(first.description, "チャンネル: Chan\n\ndesc");
    assert_eq!(
        first.pub_date,
        Some(DateTime::parse_from_rfc3339("2026-11-01T10:00:00Z").unwrap())
    );

    let second = &feed.items[1];
    assert_eq!(second.title, "無題");
    assert_eq!(second.description, "", "説明もチャンネルもなければ空");
    assert_eq!(second.pub_date, Some(now()), "解釈できない日時は現在時刻");
}

#[test]
fn description_is_cut_at_300_chars_and_channel_only_when_empty() {
    let long = "あ".repeat(301);
    let exact = "い".repeat(300);
    let json = body(&[
        video(Some("a"), Some("t"), &long, "", "2026-11-01T10:00:00Z"),
        video(Some("b"), Some("t"), &exact, "", "2026-11-01T10:00:00Z"),
        video(Some("c"), Some("t"), "", "Chan", "2026-11-01T10:00:00Z"),
    ]);
    let feed = feed_from_response(200, &json, "q", SEARCH, 20, now()).unwrap();
    assert_eq!(
        feed.items[0].description,
        format!("{}...", "あ".repeat(300))
    );
    assert_eq!(feed.items[1].description, exact);
    assert_eq!(feed.items[2].description, "チャンネル: Chan");
}

#[test]
fn max_items_limits_the_articles_and_empty_items_is_an_empty_feed() {
    let items: Vec<String> = (0..5)
        .map(|i| video(Some(&format!("v{i}")), Some("t"), "", "", ""))
        .collect();
    let feed = feed_from_response(200, &body(&items), "q", SEARCH, 2, now()).unwrap();
    assert_eq!(feed.items.len(), 2);

    let empty = feed_from_response(200, br#"{"items":[]}"#, "q", SEARCH, 20, now()).unwrap();
    assert!(
        empty.items.is_empty(),
        "API の成功で 0 件なら、空のフィード"
    );
}

// ---- Y-7: エラーの対応 ----

fn error_message(status: u16, body: &[u8]) -> String {
    match feed_from_response(status, body, "q", SEARCH, 20, now()) {
        Err(FeedError::YouTube(message)) => message,
        other => panic!("YouTube のエラーのはずが {other:?}"),
    }
}

#[test]
fn api_failures_are_errors_with_reasons_not_empty_feeds() {
    let quota = br#"{"error":{"code":403,"errors":[{"reason":"quotaExceeded"}]}}"#;
    let invalid = br#"{"error":{"code":400,"errors":[{"reason":"badRequest"}],"details":[{"reason":"API_KEY_INVALID"}]}}"#;
    let key_invalid = br#"{"error":{"code":403,"errors":[{"reason":"keyInvalid"}]}}"#;
    let cases: [(u16, &[u8], &str); 6] = [
        (403, quota, "YouTube API のクォータを超過しました"),
        (400, invalid, "YouTube API キーが無効です"),
        (403, key_invalid, "YouTube API キーが無効です"),
        (
            500,
            b"oops",
            "YouTube API の呼び出しに失敗しました (HTTP 500)",
        ),
        (
            200,
            b"not json",
            "YouTube API の呼び出しに失敗しました (HTTP 200)",
        ),
        (
            200,
            br#"{"items":{}}"#,
            "YouTube API の呼び出しに失敗しました (HTTP 200)",
        ),
    ];
    for (status, body, expected) in cases {
        let message = error_message(status, body);
        assert_eq!(message, expected, "{status}");
        assert!(!message.contains(KEY));
    }
}

// ---- パイプライン (偽サーバー) ----

fn generator(server: &ProbeServer, key: Option<&str>) -> FeedGenerator<LocalLookup> {
    FeedGenerator::with_fetcher(lenient_fetcher())
        .with_youtube_api_key(key.map(str::to_string))
        .with_youtube_endpoint(format!(
            "http://api.test:{}/youtube/v3/search",
            server.addr.port()
        ))
}

fn options(max_items: usize, use_feed: bool) -> GenerateOptions {
    GenerateOptions {
        max_items,
        user_agent: "test-agent/1.0".to_string(),
        use_feed,
        feed_first: use_feed,
    }
}

#[tokio::test]
async fn a_search_url_is_answered_from_the_api_without_fetching_youtube() {
    let json = body(&[video(
        Some("v1"),
        Some("Hello"),
        "d",
        "C",
        "2026-11-01T10:00:00Z",
    )]);
    let server = probe_server::spawn(vec![Route::page(
        "/youtube/v3/search",
        "application/json",
        json,
    )])
    .await;

    let outcome = generator(&server, Some(KEY))
        .generate(SEARCH, &options(7, true), now())
        .await
        .unwrap();

    let Outcome::Generated { feed, detected } = outcome else {
        panic!("Generated のはず");
    };
    assert!(detected.is_empty(), "use_feed / feed_first は無視する");
    assert_eq!(feed.items[0].link, "https://www.youtube.com/watch?v=v1");
    assert_eq!(feed.items[0].guid.as_deref(), Some("youtube-video-v1"));

    let requests = server.requests();
    assert_eq!(requests.len(), 1, "API を 1 回だけ呼ぶ: {requests:?}");
    let path = &requests[0].1;
    assert!(path.starts_with("/youtube/v3/search?"), "{path}");
    assert!(path.contains("maxResults=7"), "{path}");
    assert_eq!(server.user_agents(), ["test-agent/1.0"]);
}

#[tokio::test]
async fn without_a_key_it_fails_and_makes_no_request() {
    let server = probe_server::spawn(vec![]).await;
    for key in [None, Some("")] {
        let result = generator(&server, key)
            .generate(SEARCH, &options(20, false), now())
            .await;
        match result {
            Err(FeedError::YouTube(message)) => {
                assert_eq!(message, "YouTube の検索には API キーの設定が必要です");
            }
            other => panic!("キー未設定のエラーのはずが {other:?}"),
        }
    }
    assert!(server.requests().is_empty(), "リクエストを 1 回もしない");
}

#[tokio::test]
async fn an_api_failure_is_an_error_without_the_key() {
    let server = probe_server::spawn(vec![
        Route::new("/youtube/v3/search", 500, "application/json").with_body("boom"),
    ])
    .await;
    let result = generator(&server, Some(KEY))
        .generate(SEARCH, &options(20, false), now())
        .await;
    let Err(error) = result else {
        panic!("エラーのはず (空のフィードにしない)");
    };
    assert!(matches!(error, FeedError::YouTube(_)));
    assert!(!error.to_string().contains(KEY));
    assert!(!error.to_string().contains("boom"), "応答の本文を含めない");
}

#[tokio::test]
async fn a_refused_api_address_keeps_the_fetch_layer_error_without_the_key() {
    // SSRF 対策の層を通っていること: 127.0.0.1 を通さない取得器では、拒否される。
    let server = probe_server::spawn(vec![]).await;
    let generator = FeedGenerator::with_fetcher(probe_server::refusing_fetcher())
        .with_youtube_api_key(Some(KEY.to_string()))
        .with_youtube_endpoint(format!("http://api.test:{}/search", server.addr.port()));
    let error = generator
        .generate(SEARCH, &options(20, false), now())
        .await
        .unwrap_err();
    assert!(matches!(error, FeedError::UnsafeUrl(_)), "{error:?}");
    assert!(!error.to_string().contains(KEY));
    assert!(server.requests().is_empty());
}
