//! `parse_feed_query` (docs/specs/api.md A-2、A-4)。

use axum::http::StatusCode;
use feedgen_server::query::{ApiError, parse_feed_query};

fn pairs(items: &[(&str, &str)]) -> Vec<(String, String)> {
    items
        .iter()
        .map(|(k, v)| (k.to_string(), v.to_string()))
        .collect()
}

fn status_of(items: &[(&str, &str)]) -> StatusCode {
    parse_feed_query(&pairs(items)).unwrap_err().status
}

#[test]
fn defaults() {
    let request = parse_feed_query(&pairs(&[("url", "https://example.com/")])).unwrap();
    assert_eq!(request.url, "https://example.com/");
    assert_eq!(request.options.max_items, 20);
    assert!(!request.options.use_feed);
    assert!(!request.options.feed_first);
    assert_eq!(request.options.user_agent, "feedgen-api/1.0");
}

#[test]
fn explicit_values() {
    let request = parse_feed_query(&pairs(&[
        ("url", "https://example.com/"),
        ("max_items", "5"),
        ("use_feed", "true"),
        ("feed_first", "1"),
        ("user_agent", "my agent/2"),
    ]))
    .unwrap();
    assert_eq!(request.options.max_items, 5);
    assert!(request.options.use_feed);
    assert!(request.options.feed_first);
    assert_eq!(request.options.user_agent, "my agent/2");
}

#[test]
fn missing_url_is_422() {
    let error = parse_feed_query(&pairs(&[("max_items", "5")])).unwrap_err();
    assert_eq!(error.status, StatusCode::UNPROCESSABLE_ENTITY);
    assert!(error.detail.contains("url"));
}

#[test]
fn max_items_boundaries() {
    for ok in ["1", "100"] {
        assert!(parse_feed_query(&pairs(&[("url", "https://e.com/"), ("max_items", ok)])).is_ok());
    }
    for bad in ["0", "101", "-1", "abc", "", "1.5"] {
        let error =
            parse_feed_query(&pairs(&[("url", "https://e.com/"), ("max_items", bad)])).unwrap_err();
        assert_eq!(error.status, StatusCode::UNPROCESSABLE_ENTITY, "{bad:?}");
        assert!(error.detail.contains("max_items"), "{bad:?}");
    }
}

#[test]
fn boolean_aliases_are_case_insensitive() {
    for truthy in ["true", "TRUE", "True", "1", "on", "t", "y", "yes", "YES"] {
        let request =
            parse_feed_query(&pairs(&[("url", "https://e.com/"), ("use_feed", truthy)])).unwrap();
        assert!(request.options.use_feed, "{truthy}");
    }
    for falsy in ["false", "FALSE", "0", "off", "f", "n", "no", "No"] {
        let request =
            parse_feed_query(&pairs(&[("url", "https://e.com/"), ("use_feed", falsy)])).unwrap();
        assert!(!request.options.use_feed, "{falsy}");
    }
}

#[test]
fn invalid_boolean_is_422() {
    for name in ["use_feed", "feed_first"] {
        for bad in ["maybe", "", "2", "truee"] {
            let error =
                parse_feed_query(&pairs(&[("url", "https://e.com/"), (name, bad)])).unwrap_err();
            assert_eq!(
                error.status,
                StatusCode::UNPROCESSABLE_ENTITY,
                "{name}={bad:?}"
            );
            assert!(error.detail.contains(name));
        }
    }
}

#[test]
fn url_length_boundary_is_400() {
    let ok = format!("https://example.com/{}", "a".repeat(2048 - 20));
    assert_eq!(ok.len(), 2048);
    assert!(parse_feed_query(&pairs(&[("url", &ok)])).is_ok());
    let too_long = format!("{ok}a");
    assert_eq!(status_of(&[("url", &too_long)]), StatusCode::BAD_REQUEST);
}

#[test]
fn invalid_user_agent_is_400() {
    for bad in ["", "日本語", "a\nb", &"a".repeat(257)] {
        assert_eq!(
            status_of(&[("url", "https://e.com/"), ("user_agent", bad)]),
            StatusCode::BAD_REQUEST,
            "{bad:?}"
        );
    }
}

#[test]
fn ignored_and_unknown_parameters_are_accepted() {
    let request = parse_feed_query(&pairs(&[
        ("url", "https://e.com/"),
        ("google_news_interval", "1"),
        ("google_news_timeout", "10"),
        ("google_news_cache_ttl", "86400"),
        ("google_news_cache_type", "memory"),
        ("google_news_cache_enabled", "whatever"),
        ("translation_api_key", "x"),
        ("translation_target_lang", "en"),
        ("decode_google_news", "false"),
        ("translate", "false"),
        ("totally_unknown", "1"),
    ]))
    .unwrap();
    assert_eq!(request.options.max_items, 20);
}

#[test]
fn unsupported_features_are_400_naming_the_feature() {
    for name in ["decode_google_news", "translate"] {
        let error: ApiError =
            parse_feed_query(&pairs(&[("url", "https://e.com/"), (name, "true")])).unwrap_err();
        assert_eq!(error.status, StatusCode::BAD_REQUEST, "{name}");
        assert!(error.detail.contains(name), "{name}: {}", error.detail);
    }
}

#[test]
fn first_value_wins_for_duplicate_names() {
    let request = parse_feed_query(&pairs(&[
        ("url", "https://first.example/"),
        ("url", "https://second.example/"),
    ]))
    .unwrap();
    assert_eq!(request.url, "https://first.example/");
}
