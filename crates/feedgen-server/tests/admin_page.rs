//! 管理ページの HTML の、壊れたときにすぐ気づける範囲の検査 (docs/specs/admin.md M-3、M-4、M-5、M-8)。
//! 画面の細部と、ブラウザの API に依存する動作は、自動テストにせず、実装のときにブラウザで確かめる。

use feedgen_server::admin::PAGE;

#[test]
fn page_is_a_complete_html_document() {
    let lower = PAGE.to_lowercase();
    assert!(lower.contains("<!doctype html"), "doctype");
    assert!(lower.contains("<title>") && lower.contains("</title>"));
    assert!(lower.contains("charset"), "文字コードの指定");
    assert!(
        PAGE.len() < 20_000,
        "最小の 1 枚 (約 100 行のスクリプト) に収める"
    );
}

#[test]
fn page_has_the_four_inputs() {
    assert_eq!(
        PAGE.matches("type=\"checkbox\"").count(),
        2,
        "use_feed と feed_first"
    );
    for id in ["url", "max-items", "use-feed", "feed-first"] {
        assert!(PAGE.contains(&format!("id=\"{id}\"")), "id={id}");
    }
    assert!(
        !PAGE.contains("user_agent") && !PAGE.contains("user-agent"),
        "user_agent は入力に持たない"
    );
}

#[test]
fn page_builds_urls_from_the_page_origin_not_a_configured_base() {
    assert!(PAGE.contains("location.origin"));
    assert!(PAGE.contains("/feed"));
    assert!(!PAGE.contains("auto.fuga.jp") && !PAGE.contains("api_base_url"));
}

#[test]
fn page_loads_no_external_resources() {
    let lower = PAGE.to_lowercase();
    for needle in [
        "src=\"http",
        "src='http",
        "href=\"http",
        "href='http",
        "url(http",
        "@import",
        "<link",
        "<iframe",
        "<img",
        "<form",
    ] {
        assert!(!lower.contains(needle), "外部のリソースの疑い: {needle}");
    }
    for needle in ["<script src", "import(", "importscripts"] {
        assert!(!lower.contains(needle), "{needle}");
    }
}

#[test]
fn page_renders_untrusted_text_only_as_text() {
    assert!(
        PAGE.contains("textContent"),
        "取得先由来の文字列は textContent で表示する"
    );
    for forbidden in [
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval(",
        "new Function",
    ] {
        assert!(!PAGE.contains(forbidden), "{forbidden}");
    }
}

#[test]
fn page_links_are_limited_to_http_and_https_with_safe_rel() {
    assert!(PAGE.contains("noopener") && PAGE.contains("noreferrer"));
    assert!(PAGE.contains("_blank"));
    assert!(
        PAGE.contains("http:") && PAGE.contains("https:"),
        "スキームを検査する"
    );
}

#[test]
fn page_url_parameter_order_matches_the_cli() {
    // 「url、max_items、use_feed、feed_first」の順に、指定されたものだけを入れる (M-5)。
    let position = |s: &str| PAGE.find(s).unwrap_or_else(|| panic!("見つからない: {s}"));
    assert!(position("max_items") < position("use_feed"));
    assert!(position("use_feed") < position("feed_first"));
    assert!(PAGE.contains("URLSearchParams"));
}
