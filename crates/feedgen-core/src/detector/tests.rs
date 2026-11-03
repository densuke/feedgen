//! docs/specs/detector.md のテスト (RED)。
//!
//! 軽い判定 (HTML の `<link>`、本文のルート要素、`Content-Type`) は表で総当たりし、
//! 重いもの (共通パスの確認。ローカルサーバーを使う) は関心ごとにまとめて本数を絞る。

use std::io;
use std::net::IpAddr;
use std::time::{Duration, Instant};

use super::probe_server::{self, ProbeServer, Route};
use super::*;
use crate::fetch::{Limits, Lookup, SafeFetcher};

const BASE: &str = "https://example.com/blog/post.html";

// ---- D-1、D-2: HTML の <link> ----

type Found = (String, String, &'static str);

fn feeds_in(html: &str, base: &str) -> Vec<Found> {
    detect_from_html(html, base)
        .into_iter()
        .map(|f| (f.url, f.title, f.kind.label()))
        .collect()
}

fn feeds(links: &str) -> Vec<Found> {
    feeds_in(
        &format!("<html><head>{links}</head><body></body></html>"),
        BASE,
    )
}

fn first_url(links: &str) -> Option<String> {
    feeds(links).into_iter().next().map(|f| f.0)
}

#[test]
fn kind_is_decided_from_the_type_attribute() {
    let cases = [
        ("application/rss+xml", "RSS"),
        ("application/atom+xml", "Atom"),
        ("application/xml", "XML"),
        ("text/xml", "XML"),
        ("application/json", "JSON"),
        ("application/feed+json", "JSON"), // Python 版は検出しない。直す
        ("APPLICATION/RSS+XML", "RSS"),
        ("application/rss+xml; charset=utf-8", "RSS"),
        ("application/atom+xml;charset=UTF-8", "Atom"),
        ("  Application/RSS+XML  ", "RSS"), // 前後の空白は除く
    ];
    for (ty, label) in cases {
        let found = feeds(&format!(r#"<link rel="alternate" type="{ty}" href="/f">"#));
        assert_eq!(found.len(), 1, "type={ty:?}: {found:?}");
        assert_eq!(found[0].2, label, "type={ty:?}");
    }
}

#[test]
fn non_feed_types_are_ignored() {
    for ty in [
        "text/html",
        "",
        "application/xhtml+xml",
        "text/plain",
        // 前方一致する別の型は拾わない (完全一致にする)
        "application/xml-dtd",
        "text/xml-external-parsed-entity",
        "application/jsonl",
        "application/rss+xml-x",
    ] {
        let html = format!(r#"<link rel="alternate" type="{ty}" href="/f">"#);
        assert!(feeds(&html).is_empty(), "type={ty:?}");
    }
    // type 属性がない
    assert!(feeds(r#"<link rel="alternate" href="/f">"#).is_empty());
}

#[test]
fn rel_tokens_are_matched_without_regard_to_case() {
    // Python 版は大文字小文字を区別して、ALTERNATE を検出しない。HTML の仕様どおり、区別しない (直す)。
    for rel in [
        "alternate",
        "ALTERNATE",
        "Alternate",
        "alternate stylesheet",
        "stylesheet alternate",
        "  alternate  ",
    ] {
        let html = format!(r#"<link rel="{rel}" type="application/rss+xml" href="/f">"#);
        assert_eq!(feeds(&html).len(), 1, "rel={rel:?}");
    }
    for rel in ["alternate-x", "stylesheet", "alt", ""] {
        let html = format!(r#"<link rel="{rel}" type="application/rss+xml" href="/f">"#);
        assert!(feeds(&html).is_empty(), "rel={rel:?}");
    }
    // rel 属性がない
    assert!(feeds(r#"<link type="application/rss+xml" href="/f">"#).is_empty());
}

#[test]
fn href_is_resolved_against_the_base_url() {
    let cases = [
        ("/f", "https://example.com/f"),
        ("f.xml", "https://example.com/blog/f.xml"),
        ("../f.xml", "https://example.com/f.xml"),
        ("//cdn.example.org/f", "https://cdn.example.org/f"),
        ("https://other.example/f", "https://other.example/f"),
        // 前後の空白は取り除く (Python 版は末尾に空白が残る。直す)
        ("  /f  ", "https://example.com/f"),
        ("\n/f\t", "https://example.com/f"), // ASCII の空白 (改行、タブ) も除く
        // NBSP は ASCII の空白ではないので除かない (HTML の URL の扱い)。URL では % エンコードされる
        ("/a\u{a0}", "https://example.com/a%C2%A0"),
        // fragment は除く
        ("/f#b", "https://example.com/f"),
    ];
    for (href, expected) in cases {
        let html = format!(r#"<link rel="alternate" type="application/rss+xml" href="{href}">"#);
        assert_eq!(first_url(&html).as_deref(), Some(expected), "href={href:?}");
    }
}

#[test]
fn unusable_href_values_are_dropped() {
    // Python 版は javascript: などをそのまま URL として返す。http(s) 以外は捨てる (直す)。
    for href in [
        "",
        "   ",
        "javascript:x",
        "mailto:a@b.c",
        "data:text/xml,x",
        "ftp://example.com/f",
        // ページ自身を指す (fragment を除くと基準 URL と同じ)
        "#",
        "#top",
        "post.html#x",
        // 認証部つき
        "http://a:b@h.example/f",
    ] {
        let html = format!(r#"<link rel="alternate" type="application/rss+xml" href="{href}">"#);
        assert!(feeds(&html).is_empty(), "href={href:?}");
    }
    // href 属性がない
    assert!(feeds(r#"<link rel="alternate" type="application/rss+xml">"#).is_empty());
}

#[test]
fn urls_with_credentials_are_dropped_even_when_the_base_has_them() {
    let link = r#"<link rel="alternate" type="application/rss+xml" href="/f">"#;
    let html = format!("<html><head>{link}</head></html>");
    assert!(feeds_in(&html, "https://user:pw@example.com/p").is_empty());
    // 認証部のない基準なら出る (対照)
    assert_eq!(feeds_in(&html, "https://example.com/p").len(), 1);
}

#[test]
fn fragments_are_removed_before_deduplication() {
    let html = r#"<html><head>
        <link rel="alternate" type="application/rss+xml" title="A" href="/f#b">
        <link rel="alternate" type="application/rss+xml" title="B" href="/f">
        <link rel="alternate" type="application/rss+xml" title="C" href="/g#x">
        </head></html>"#;
    let urls: Vec<String> = feeds_in(html, BASE).into_iter().map(|f| f.0).collect();
    assert_eq!(urls, ["https://example.com/f", "https://example.com/g"]);
}

#[test]
fn title_defaults_when_missing_or_blank_and_is_trimmed() {
    let title_of = |attr: &str| {
        let html = format!(r#"<link rel="alternate" type="application/rss+xml" href="/f"{attr}>"#);
        feeds(&html).remove(0).1
    };
    assert_eq!(title_of(""), "不明なフィード");
    assert_eq!(title_of(r#" title="""#), "不明なフィード"); // Python 版は空のまま。直す
    assert_eq!(title_of(r#" title="   ""#), "不明なフィード");
    assert_eq!(title_of(r#" title="  X  ""#), "X"); // Python 版は空白が残る。直す
}

#[test]
fn results_keep_document_order_and_drop_duplicate_urls() {
    let html = r#"<html><head>
        <link rel="alternate" type="application/rss+xml" title="Comments" href="/comments">
        <link rel="alternate" type="application/atom+xml" title="Posts" href="/posts">
        <link rel="alternate" type="application/atom+xml" title="Dup" href="https://example.com/comments">
        </head><body>
        <link rel="alternate" type="application/rss+xml" title="In body" href="/in-body">
        </body></html>"#;
    let found = feeds_in(html, BASE);
    let urls: Vec<&str> = found.iter().map(|f| f.0.as_str()).collect();
    assert_eq!(
        urls,
        [
            "https://example.com/comments",
            "https://example.com/posts",
            "https://example.com/in-body"
        ]
    );
    // 重複は、最初の 1 件 (タイトルと種類も最初のもの) を残す
    assert_eq!(found[0].1, "Comments");
    assert_eq!(found[0].2, "RSS");
}

#[test]
fn livedoor_style_page_yields_rss_then_atom() {
    // 実サイト (mfujin、kabumatome) と同じ形: RSS 1.0 (index.rdf) と Atom (atom.xml)
    let html = r#"<html><head>
        <link rel="alternate" type="application/rss+xml" title="RSS" href="https://blog.example/index.rdf">
        <link rel="alternate" type="application/atom+xml" title="Atom" href="https://blog.example/atom.xml">
        </head></html>"#;
    assert_eq!(
        feeds_in(html, "https://blog.example/"),
        [
            (
                "https://blog.example/index.rdf".to_string(),
                "RSS".to_string(),
                "RSS"
            ),
            (
                "https://blog.example/atom.xml".to_string(),
                "Atom".to_string(),
                "Atom"
            ),
        ]
    );
}

#[test]
fn a_feed_itself_and_pages_without_links_yield_nothing() {
    let rdf =
        r#"<?xml version="1.0"?><rdf:RDF><channel><link>https://x/</link></channel></rdf:RDF>"#;
    assert!(feeds_in(rdf, BASE).is_empty());
    assert!(feeds_in("", BASE).is_empty());
    assert!(feeds_in("<<<>>>", BASE).is_empty());
    assert!(feeds_in("<html><head><title>T</title></head></html>", BASE).is_empty());
}

// ---- D-5: 本文のルート要素 ----

fn root(body: &[u8]) -> Option<RootKind> {
    feed_root(body)
}

#[test]
fn rss_atom_and_rdf_roots_are_recognized() {
    assert_eq!(
        root(b"<rss version=\"2.0\"><channel/></rss>"),
        Some(RootKind::Rss)
    );
    assert_eq!(
        root(b"<?xml version=\"1.0\"?>\n<rss version=\"2.0\"></rss>"),
        Some(RootKind::Rss)
    );
    assert_eq!(
        root(b"<rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\"></rdf:RDF>"),
        Some(RootKind::Rdf)
    );
    assert_eq!(
        root(b"<RDF xmlns=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\"></RDF>"),
        Some(RootKind::Rdf)
    );
    assert_eq!(
        root(b"<feed xmlns=\"http://www.w3.org/2005/Atom\"></feed>"),
        Some(RootKind::Atom)
    );
    assert_eq!(
        root(b"<atom:feed xmlns:atom=\"http://www.w3.org/2005/Atom\"></atom:feed>"),
        Some(RootKind::Atom)
    );
}

#[test]
fn prolog_is_skipped_before_the_root() {
    let rss = |prefix: &[u8]| {
        let mut body = prefix.to_vec();
        body.extend_from_slice(b"<rss version=\"2.0\"></rss>");
        root(&body)
    };
    assert_eq!(rss(b"\xEF\xBB\xBF"), Some(RootKind::Rss)); // BOM
    assert_eq!(rss(b"  \r\n\t "), Some(RootKind::Rss)); // 空白
    assert_eq!(
        rss(b"<?xml version=\"1.0\" encoding=\"UTF-8\"?>"),
        Some(RootKind::Rss)
    );
    assert_eq!(
        rss(b"<?xml version=\"1.0\"?><?xml-stylesheet type=\"text/xsl\" href=\"a.xsl\"?>"),
        Some(RootKind::Rss)
    );
    assert_eq!(
        rss(b"<!-- a comment with <rss> inside -->"),
        Some(RootKind::Rss)
    );
    assert_eq!(
        rss(b"<!DOCTYPE rss [<!ENTITY x \"y\"><!-- ] -->]>"),
        Some(RootKind::Rss),
        "DOCTYPE の内部サブセット"
    );
    assert_eq!(
        rss(b"\xEF\xBB\xBF <?xml version=\"1.0\"?>\n<!-- c -->\n<!DOCTYPE rss>\n"),
        Some(RootKind::Rss)
    );
}

#[test]
fn html_and_other_documents_are_not_feeds() {
    let cases: [(&str, &[u8]); 12] = [
        ("HTML5", b"<!DOCTYPE html><html><head></head></html>"),
        ("html 要素", b"<html><body>hi</body></html>"),
        (
            "XHTML (Content-Type が xml でも、ルートは html)",
            b"<?xml version=\"1.0\"?><!DOCTYPE html PUBLIC \"-//W3C//DTD XHTML 1.0//EN\" \"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd\"><html xmlns=\"http://www.w3.org/1999/xhtml\"></html>",
        ),
        ("空", b""),
        ("空白だけ", b"  \r\n  "),
        ("テキスト", b"hello world"),
        ("JSON Feed", b"{\"version\":\"https://jsonfeed.org/version/1.1\"}"),
        ("大文字の RSS (XML は大文字小文字を区別する)", b"<RSS version=\"2.0\"></RSS>"),
        ("名前が似ている (feedback)", b"<feedback></feedback>"),
        ("名前が似ている (rssx)", b"<rssx></rssx>"),
        ("UTF-16 (BOM つき)", b"\xFF\xFE<\0r\0s\0s\0>\0"),
        ("終わらないコメント", b"<!-- <rss></rss>"),
    ];
    for (label, body) in cases {
        assert_eq!(root(body), None, "{label}");
    }
}

#[test]
fn only_the_first_64_kib_are_scanned() {
    let mut body = b"<!--".to_vec();
    body.extend(std::iter::repeat_n(b'x', 70 * 1024));
    body.extend_from_slice(b"--><rss version=\"2.0\"></rss>");
    assert_eq!(root(&body), None);

    let mut short = b"<!--".to_vec();
    short.extend(std::iter::repeat_n(b'x', 60 * 1024));
    short.extend_from_slice(b"--><rss version=\"2.0\"></rss>");
    assert_eq!(root(&short), Some(RootKind::Rss));
}

// ---- D-6: 代理取得の Content-Type ----

#[test]
fn proxied_content_type_follows_the_root_and_keeps_the_charset() {
    let cases = [
        (RootKind::Rss, "application/xml", "application/rss+xml"),
        (RootKind::Rdf, "text/xml", "application/rss+xml"),
        (RootKind::Atom, "application/xml", "application/atom+xml"),
        (RootKind::Atom, "", "application/atom+xml"),
        (
            RootKind::Rdf,
            "application/xml; charset=UTF-8",
            "application/rss+xml; charset=UTF-8",
        ),
        (
            RootKind::Rss,
            "text/xml;Charset=Shift_JIS",
            "application/rss+xml; charset=Shift_JIS",
        ),
        (
            RootKind::Atom,
            "application/atom+xml; boundary=x; charset=utf-8",
            "application/atom+xml; charset=utf-8",
        ),
    ];
    for (root, original, expected) in cases {
        assert_eq!(
            proxied_content_type(root, original),
            expected,
            "{original:?}"
        );
    }
}

// ---- D-3、D-4: 共通パスの確認 (ローカルサーバー) ----

/// どの名前でも 127.0.0.1 に解決する。
struct LocalLookup;

impl Lookup for LocalLookup {
    async fn lookup(&self, _host: &str) -> io::Result<Vec<IpAddr>> {
        Ok(vec![IpAddr::from([127, 0, 0, 1])])
    }
}

fn lenient() -> SafeFetcher<LocalLookup> {
    SafeFetcher::for_test(
        LocalLookup,
        vec![IpAddr::from([127, 0, 0, 1])],
        Limits::default(),
    )
}

fn site(server: &ProbeServer, path: &str) -> String {
    format!("http://site.test:{}{path}", server.addr.port())
}

/// (パス, タイトル, 種類) にする。
fn found_at(
    server: &ProbeServer,
    info: Option<FeedInfo>,
) -> Option<(String, String, &'static str)> {
    let prefix = format!("http://site.test:{}", server.addr.port());
    info.map(|f| (f.url.replacen(&prefix, "", 1), f.title, f.kind.label()))
}

fn title(server: &ProbeServer, label: &str) -> String {
    format!("site.test:{} - {label}", server.addr.port())
}

#[tokio::test]
async fn html_responses_are_skipped_and_the_first_feed_wins() {
    let server = probe_server::spawn(vec![
        Route::new("/feed", 200, "text/html"),
        Route::new("/rss", 200, "application/rss+xml"),
        Route::new("/atom.xml", 200, "application/atom+xml"),
    ])
    .await;

    let info = probe_common_paths(&lenient(), &site(&server, "/")).await;
    assert_eq!(
        found_at(&server, info),
        Some(("/rss".to_string(), title(&server, "RSS"), "RSS"))
    );
}

#[tokio::test]
async fn earlier_path_wins_even_when_a_later_one_is_also_a_feed() {
    // 先頭の /feed は応答が遅く、後ろの /atom.xml は即答する。「先に完了したもの」ではなく、
    // 「リストの順序で早いもの」が選ばれること。
    let server = probe_server::spawn(vec![
        Route::new("/feed", 200, "application/xml").delayed(Duration::from_millis(300)),
        Route::new("/atom.xml", 200, "application/atom+xml"),
    ])
    .await;

    let info = probe_common_paths(&lenient(), &site(&server, "/")).await;
    // /feed は application/xml なので、パスで補って RSS
    assert_eq!(
        found_at(&server, info),
        Some(("/feed".to_string(), title(&server, "RSS"), "RSS"))
    );
}

#[tokio::test]
async fn kind_follows_the_content_type_then_the_path() {
    let cases = [
        ("/feed", "application/json", "JSON"), // Python 版は RSS (パスで決める)。直す
        ("/feed.xml", "application/atom+xml", "Atom"),
        ("/rss.xml", "application/atom+xml", "Atom"),
        ("/feed", "application/rss+xml; charset=utf-8", "RSS"),
        ("/atom.xml", "application/xml", "Atom"), // Content-Type が xml だけなら、パスで補う
        ("/rss.xml", "text/xml", "RSS"),
        ("/feed", "application/xml", "RSS"),
    ];
    for (path, content_type, label) in cases {
        let server = probe_server::spawn(vec![Route::new(path, 200, content_type)]).await;
        let info = probe_common_paths(&lenient(), &site(&server, "/")).await;
        assert_eq!(
            found_at(&server, info),
            Some((path.to_string(), title(&server, label), label)),
            "{path} {content_type}"
        );
    }
}

#[tokio::test]
async fn unsuitable_responses_are_not_feeds() {
    let cases = [
        ("404 の xml", 404, "application/xml"),
        (
            "XHTML (xml を含むが html も含む)",
            200,
            "application/xhtml+xml",
        ),
        ("text/html", 200, "text/html; charset=utf-8"),
        ("text/plain", 200, "text/plain"),
        ("202 の xml (200 だけが成功)", 202, "application/rss+xml"),
        ("HEAD を拒否 (405)", 405, ""),
        // パラメータにだけ xml がある値は、フィードとみなさない
        (
            "octet-stream の filename に xml",
            200,
            "application/octet-stream; filename=feed.xml",
        ),
        ("text/plain の format に xml", 200, "text/plain; format=xml"),
    ];
    for (label, status, content_type) in cases {
        let server = probe_server::spawn(vec![Route::new("/feed", status, content_type)]).await;
        let info = probe_common_paths(&lenient(), &site(&server, "/")).await;
        assert_eq!(info, None, "{label}");
    }
}

#[tokio::test]
async fn the_site_root_is_probed_not_the_page_path() {
    let server = probe_server::spawn(vec![]).await;

    let info = probe_common_paths(&lenient(), &site(&server, "/deep/path/page.html?x=1")).await;
    assert_eq!(info, None);

    let mut requests = server.requests();
    requests.sort();
    let mut expected: Vec<(String, String)> = [
        "/feed",
        "/rss",
        "/atom.xml",
        "/rss.xml",
        "/feed.xml",
        "/feeds/all.atom.xml",
        "/rss/index.xml",
        "/feed/index.xml",
    ]
    .iter()
    .map(|p| ("HEAD".to_string(), p.to_string()))
    .collect();
    expected.sort();
    assert_eq!(requests, expected, "ルートの 8 本を HEAD で確かめる");
}

#[tokio::test]
async fn probes_run_in_parallel() {
    // 8 本とも 800 ミリ秒かかる。順番に試すと 6.4 秒以上、並列なら 1 秒前後。
    let delay = Duration::from_millis(800);
    let mut routes: Vec<Route> = [
        "/feed",
        "/rss",
        "/atom.xml",
        "/rss.xml",
        "/feeds/all.atom.xml",
        "/rss/index.xml",
        "/feed/index.xml",
    ]
    .into_iter()
    .map(|path| Route::new(path, 404, "").delayed(delay))
    .collect();
    routes.push(Route::new("/feed.xml", 200, "application/rss+xml").delayed(delay));
    let server = probe_server::spawn(routes).await;

    let started = Instant::now();
    let info = probe_common_paths(&lenient(), &site(&server, "/")).await;
    let elapsed = started.elapsed();

    assert_eq!(
        found_at(&server, info).map(|f| f.0),
        Some("/feed.xml".to_string())
    );
    assert!(elapsed < Duration::from_secs(3), "並列でない: {elapsed:?}");
}

#[tokio::test]
async fn a_probe_that_exceeds_its_timeout_counts_as_missing() {
    // /feed は 5 秒かかる (1 本の締切 300 ミリ秒で打ち切る)。/rss はすぐ返る。
    let server = probe_server::spawn(vec![
        Route::new("/feed", 200, "application/rss+xml").delayed(Duration::from_secs(5)),
        Route::new("/rss", 200, "application/rss+xml"),
    ])
    .await;

    let started = Instant::now();
    let info =
        probe_common_paths_with(&lenient(), &site(&server, "/"), Duration::from_millis(300)).await;
    let elapsed = started.elapsed();

    assert_eq!(
        found_at(&server, info).map(|f| f.0),
        Some("/rss".to_string())
    );
    assert!(
        elapsed < Duration::from_secs(2),
        "締切が効かない: {elapsed:?}"
    );
}

#[tokio::test]
async fn refused_targets_are_missing_not_errors_and_never_connected() {
    // 許可アドレスが空だと、ポート検査 (80/443 のみ) で先に止まり、IP の検査に届かない。
    // 別のアドレスだけを許可すると、ポートの制限は外れ、127.0.0.1 は IP の検査で拒否される。
    let strict = SafeFetcher::for_test(
        LocalLookup,
        vec![IpAddr::from([10, 0, 0, 9])],
        Limits::default(),
    );
    let server = probe_server::spawn(vec![Route::new("/feed", 200, "application/rss+xml")]).await;

    let info = probe_common_paths(&strict, &site(&server, "/")).await;
    assert_eq!(info, None);
    assert!(
        server.requests().is_empty(),
        "拒否した相手に接続してはいけない"
    );
}
