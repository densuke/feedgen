//! Python 版と挙動を変えた箇所の手書きテスト (docs/specs/parser.md P-2〜P-6、6 章)。
//!
//! Python 版の出力と一致させるテストは tests/parser_golden.rs にある。ここでは、
//! 「壊れた挙動は直す」方針で変えた点の期待値を、理由つきで手書きする。

use chrono::{DateTime, FixedOffset, TimeZone};

use super::*;

const BASE: &str = "https://example.com/";

fn now() -> DateTime<FixedOffset> {
    FixedOffset::east_opt(0)
        .expect("オフセットが不正")
        .with_ymd_and_hms(2026, 11, 3, 0, 0, 0)
        .single()
        .expect("日時が不正")
}

fn run(html: &str) -> (Metadata, Vec<RssItem>) {
    parse(html, BASE, 20, now())
}

// ---- P-3: メタデータ ----

#[test]
fn title_is_untitled_only_when_the_element_is_missing() {
    assert_eq!(run("<html><body></body></html>").0.title, "無題");
    // 空の <title> は空のまま (Python 版も同じ)
    assert_eq!(run("<html><head><title></title></head></html>").0.title, "");
}

#[test]
fn metadata_link_is_the_given_base_url() {
    assert_eq!(run("<html></html>").0.link, BASE);
}

#[test]
fn short_first_paragraph_is_used_without_an_ellipsis() {
    // Python 版は短くても必ず "..." を付ける。直す (P-3)。
    assert_eq!(
        run("<html><body><p>short</p></body></html>").0.description,
        "short"
    );
    // 空の <p> は空の説明 (Python 版は "...")
    assert_eq!(run("<html><body><p></p></body></html>").0.description, "");
    // <p> がなければ空
    assert_eq!(run("<html><body></body></html>").0.description, "");
}

#[test]
fn long_first_paragraph_is_cut_at_200_characters_with_an_ellipsis() {
    let html = format!("<html><body><p>{}</p></body></html>", "a".repeat(250));
    assert_eq!(run(&html).0.description, format!("{}...", "a".repeat(200)));
    // ちょうど 200 文字なら切り詰めないので "..." は付かない
    let exact = format!("<html><body><p>{}</p></body></html>", "a".repeat(200));
    assert_eq!(run(&exact).0.description, "a".repeat(200));
}

#[test]
fn empty_meta_description_falls_back_to_the_first_paragraph() {
    let html = r#"<html><head><meta name="description" content=""></head><body><p>fallback</p></body></html>"#;
    assert_eq!(run(html).0.description, "fallback");
}

// ---- P-4: 戦略 1 (見出し) ----

#[test]
fn heading_uses_the_first_anchor_with_a_non_empty_href() {
    // Python 版は最初の <a> の href が空だと見出しごと捨てる。直す (P-4)。
    let html = r#"<h2><a href="">x</a><a href="/y">y</a></h2>"#;
    let items = run(html).1;
    assert_eq!(items.len(), 1, "{items:?}");
    assert_eq!(items[0].title, "xy");
    assert_eq!(items[0].link, "https://example.com/y");
    assert_eq!(
        items[0].guid.as_deref(),
        Some("https://example.com/#heading-0")
    );
}

#[test]
fn heading_title_is_trimmed_including_no_break_spaces() {
    let html = "<h2><a href=\"/a\">\u{a0} T \u{a0}</a></h2>";
    assert_eq!(run(html).1[0].title, "T");
}

// ---- P-4: 戦略 2 (カード) ----

#[test]
fn card_with_an_empty_title_is_not_adopted() {
    // Python 版は空の title を採用して枠を消費し、後段の重複排除で消すので、
    // max_items = 1 のとき 0 件になる。直す (P-4)。
    let html = r#"<div class="card"><h3></h3>some text long enough</div>
                  <div class="card">Second card title text</div>"#;
    let items = parse(html, BASE, 1, now()).1;
    assert_eq!(items.len(), 1, "{items:?}");
    assert_eq!(items[0].title, "Second card title text");
    assert_eq!(items[0].link, BASE);
    assert_eq!(
        items[0].guid.as_deref(),
        Some("https://example.com/#card-0")
    );
}

// ---- P-6: URL の正規化 ----

#[test]
fn urls_are_resolved_with_join_and_non_http_schemes_become_no_link() {
    let base = "https://h.example/a/index.html";
    let hrefs = [
        "/x",                 // L0
        "javascript:void(0)", // L1: リンクなし → 見出しごと捨てる (番号は数える)
        "https://o.example/y",
        "b.html",
        "//cdn.example/z",
        "?p=2",
        "#top",
        "mailto:a@b.c", // L7: リンクなし
    ];
    let html: String = hrefs
        .iter()
        .enumerate()
        .map(|(n, href)| format!("<h2><a href=\"{href}\">L{n}</a></h2>"))
        .collect();

    let items = parse(&html, base, 20, now()).1;
    let got: Vec<(&str, &str, &str)> = items
        .iter()
        .map(|i| {
            (
                i.title.as_str(),
                i.link.as_str(),
                i.guid.as_deref().unwrap_or(""),
            )
        })
        .collect();
    let guid = |n: usize| format!("{base}#heading-{n}");
    let expected = [
        ("L0", "https://h.example/x".to_string(), guid(0)),
        ("L2", "https://o.example/y".to_string(), guid(2)),
        ("L3", "https://h.example/a/b.html".to_string(), guid(3)),
        ("L4", "https://cdn.example/z".to_string(), guid(4)),
        (
            "L5",
            "https://h.example/a/index.html?p=2".to_string(),
            guid(5),
        ),
        (
            "L6",
            "https://h.example/a/index.html#top".to_string(),
            guid(6),
        ),
    ];
    let expected: Vec<(&str, &str, &str)> = expected
        .iter()
        .map(|(t, l, g)| (*t, l.as_str(), g.as_str()))
        .collect();
    assert_eq!(got, expected);
}

// ---- 既知の差 (docs/specs/parser.md 6 章): Python 版との違いを固定する特性テスト ----
// Python 版 (BeautifulSoup の html.parser) と HTML5 の解析 (html5ever) の違い。受け入れた差で、
// scraper を更新して挙動が変わったときに気づけるよう、現在の挙動を固定している。

#[test]
fn known_difference_unknown_entity_keeps_its_semicolon() {
    // Python 版は "&unknown" (`;` が落ちる)。
    let items = run(r#"<h2><a href="/a">A &unknown; B</a></h2>"#).1;
    assert_eq!(items[0].title, "A &unknown; B");
}

#[test]
fn known_difference_cdata_content_is_dropped() {
    // Python 版は "AxB" (CDATA の中身が文字列に入る)。HTML5 ではコメント扱い。
    let items = run(r#"<h2><a href="/a">A<![CDATA[x]]>B</a></h2>"#).1;
    assert_eq!(items[0].title, "AB");
}

#[test]
fn known_difference_unclosed_paragraphs_are_not_nested() {
    // Python 版は <p> が入れ子になり、重なった記事を 5 件出す。HTML5 では <p> が自動で閉じ、3 件。
    let html = r#"<html><head><title>T</title></head><body><div><p>one<div>two <a href="/x">link text here that is long enough 123456</a></div>three</p><p>four<p>five long paragraph text that is sufficiently long to count <a href="/y">y</a></div></body></html>"#;
    let items = run(html).1;
    let titles: Vec<&str> = items.iter().map(|i| i.title.as_str()).collect();
    assert_eq!(items.len(), 3, "{titles:?}");
    assert!(titles[0].starts_with("onetwo link text here"), "{titles:?}");
    assert_eq!(titles[1], "two link text here that is long enough 123456");
    assert!(
        titles[2].starts_with("five long paragraph text"),
        "{titles:?}"
    );
}

// ---- P-1: 壊れた入力でも panic しない (Result を返さない) ----

#[test]
fn empty_and_garbage_input_do_not_panic() {
    for html in ["", "<<<>>>", "<h2><a href=", "\u{0}\u{1}", "<p>"] {
        let (metadata, items) = run(html);
        assert_eq!(metadata.link, BASE, "{html:?}");
        assert!(items.len() <= 20, "{html:?}");
    }
}

// ---- 極端な max_items でも panic しない ----

#[test]
fn huge_max_items_does_not_overflow() {
    // max_items * 2 や * 3 の掛け算が、debug ビルドで panic、release ビルドで 0 に回り込まないこと。
    let html = r#"<h2><a href="/a">A</a></h2>"#;
    for max_items in [usize::MAX, usize::MAX / 2 + 1, usize::MAX / 3 + 1] {
        let items = parse(html, BASE, max_items, now()).1;
        assert_eq!(items.len(), 1, "max_items = {max_items}");
    }
    // 0 件指定は 0 件
    assert!(parse(html, BASE, 0, now()).1.is_empty());
}

// ---- P-5: 時刻は引数の now ----

#[test]
fn every_item_gets_the_given_now() {
    let html = r#"<h2><a href="/a">A</a></h2><h2><a href="/b">B</a></h2>"#;
    let items = run(html).1;
    assert_eq!(items.len(), 2);
    assert!(items.iter().all(|i| i.pub_date == Some(now())));
}
