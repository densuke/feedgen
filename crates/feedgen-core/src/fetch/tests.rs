//! docs/specs/ssrf.md 4 章のテスト表をそのままテストにしたもの (RED)。
//!
//! 軽い判定 (文字列・アドレス) は表で総当たりし、重いもの (ローカルサーバー) は
//! 関心ごとにまとめて本数を絞る。

use std::collections::HashMap;
use std::future::Future;
use std::io;
use std::net::IpAddr;
use std::time::Duration;

use super::test_server::{self, TestServer};
use super::*;
use crate::error::FeedError;

// ---- 共通の道具 ----

fn ip(s: &str) -> IpAddr {
    s.parse().expect("テストのアドレスが不正")
}

/// 名前 → アドレスの固定表。載っていない名前は解決失敗になる。
struct FakeLookup {
    map: HashMap<String, Vec<IpAddr>>,
}

impl FakeLookup {
    fn new() -> Self {
        let local = vec![ip("127.0.0.1")];
        let entries = [
            ("pub.test", local.clone()),
            ("pub2.test", local.clone()),
            ("loopback.test", local.clone()),
            ("localhost", local.clone()),
            ("localhost.", local), // 末尾ドット付きも 127.0.0.1 に解決される
            ("internal.test", vec![ip("10.0.0.1")]),
            ("mixed.test", vec![ip("8.8.8.8"), ip("10.0.0.1")]),
            ("empty.test", vec![]),
        ];
        let map = entries
            .into_iter()
            .map(|(name, ips)| (name.to_string(), ips))
            .collect();
        Self { map }
    }

    fn with(mut self, name: &str, ips: Vec<IpAddr>) -> Self {
        self.map.insert(name.to_string(), ips);
        self
    }
}

/// 解決が締切を超えて返らない名前解決。
struct StuckLookup;

impl Lookup for StuckLookup {
    async fn lookup(&self, _host: &str) -> io::Result<Vec<IpAddr>> {
        tokio::time::sleep(Duration::from_secs(30)).await;
        Ok(vec![ip("8.8.8.8")])
    }
}

impl Lookup for FakeLookup {
    fn lookup(&self, host: &str) -> impl Future<Output = io::Result<Vec<IpAddr>>> + Send {
        let result = self
            .map
            .get(host)
            .cloned()
            .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "unknown host"));
        async move { result }
    }
}

/// 何も許可を足さない取得器。本番と同じ判定になる。
fn strict() -> SafeFetcher<FakeLookup> {
    SafeFetcher::for_test(FakeLookup::new(), vec![], Limits::default())
}

/// ローカルサーバー (127.0.0.1) だけを通す取得器。10.x などは本番と同じく拒否される。
fn lenient(limits: Limits) -> SafeFetcher<FakeLookup> {
    SafeFetcher::for_test(FakeLookup::new(), vec![ip("127.0.0.1")], limits)
}

fn url_of(server: &TestServer, path: &str) -> String {
    format!("http://pub.test:{}{}", server.addr.port(), path)
}

fn assert_unsafe(result: Result<Fetched>, what: &str) {
    assert!(
        matches!(result, Err(FeedError::UnsafeUrl(_))),
        "{what}: 拒否されるはずが {result:?}"
    );
}

/// 上限・締切・圧縮の違反は `Http` で、文面まで一致すること (S-6)。
fn assert_http(result: Result<Fetched>, message: &str) {
    assert!(
        matches!(&result, Err(FeedError::Http(m)) if m == message),
        "{message}: 期待したエラーではない {result:?}"
    );
}

// ---- S-2、S-3: URL 文字列の検査 ----

#[test]
fn check_url_rejects_ambiguous_and_unsafe_strings() {
    let rejected = [
        "http://127.0.0.1\\@8.8.8.8/", // e2 の探査 (解析差)
        "http://user:pass@example.com/",
        "http://example.com/a b",
        "http://exa\u{0}mple.com/",
        "http://exa\tmple.com/",
        "ftp://example.com/",
        "file:///etc/passwd",
        "gopher://example.com/",
        "http:///path",
        "http://",
        "",                        // e2 の探査 (空の url)
        "http:evil@8.8.8.8/?://x", // `//` を欠いた認証部
        "HTTP:evil@8.8.8.8/",
    ];
    for raw in rejected {
        assert!(check_url(raw).is_err(), "拒否されるはず: {raw:?}");
    }
}

#[test]
fn check_url_accepts_normal_urls() {
    let accepted = [
        "https://example.com/",
        "http://8.8.8.8/",
        "http://[2606:4700:4700::1111]/",
        "https://例え.jp/",
        "HTTP://example.com/",
    ];
    for raw in accepted {
        assert!(check_url(raw).is_ok(), "許可されるはず: {raw:?}");
    }
}

// ---- S-4: アドレス判定の表 ----

#[test]
fn is_public_ip_denies_every_non_public_range() {
    let denied = [
        "0.0.0.0",
        "10.1.2.3",
        "100.64.0.1",
        "127.0.0.1",
        "169.254.169.254",
        "172.16.0.1",
        "172.31.255.255",
        "192.0.0.1",
        "192.0.2.1",
        "192.168.1.1",
        "198.18.0.1",
        "198.51.100.1",
        "203.0.113.1",
        "224.0.0.1",
        "240.0.0.1",
        "255.255.255.255",
        "::",
        "::1",
        "::2",
        "fc00::1",
        "fd12::1",
        "fe80::1",
        "fec0::1",
        "ff02::1",
        "2001:db8::1",
        "100::1",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
        "64:ff9b::7f00:1",
        "64:ff9b:1::1",
        "2002:7f00:1::",
        "2001:2::1",
        "2001:10::1",
        "3fff::1",
        "::ffff:0:1:2",
        "2001:0:4136:e378:8000:63bf:3fff:fdd2",
    ];
    for s in denied {
        assert!(!is_public_ip(ip(s)), "非公開のはず: {s}");
    }
}

#[test]
fn is_public_ip_allows_public_addresses() {
    let allowed = [
        "8.8.8.8",
        "1.1.1.1",
        "93.184.216.34",
        "2606:4700:4700::1111",
        "2a00:1450:4001:81b::200e",
        "::ffff:8.8.8.8",
        "2002:0808:0808::",
    ];
    for s in allowed {
        assert!(is_public_ip(ip(s)), "公開のはず: {s}");
    }
}

// ---- S-4: 接続前の拒否 (サーバーを使わない) ----

#[tokio::test]
async fn literal_and_numeric_forms_are_denied() {
    let fetcher = strict();
    let denied = [
        "http://169.254.169.254/",
        "http://127.0.0.1:9998/",
        "http://localhost:2019/",
        "http://[::1]:9997/",
        "http://2130706433/",
        "http://0177.0.0.1/",
        "http://0x7f.1/",
        "http://10.0.0.1/",
        "http://192.168.0.1/",
        "http://100.64.0.1/",
        "http://[::ffff:127.0.0.1]/",
        "http://[64:ff9b::7f00:1]/",
        "http://[2002:7f00:1::]/",
        "http://[2001:0:4136:e378:8000:63bf:3fff:fdd2]/",
        "http://[fe80::1%25eth0]/",
        "http://[2001:2::1]/",
        "http://[2001:10::1]/",
        "http://[3fff::1]/",
        "http://[::ffff:0:1:2]/",
        "http://LOCALHOST/",
        "http://localhost./",
        "HTTP://127.0.0.1/",
        "http:evil@8.8.8.8/?://x",
        "http://127.0.0.1\\@8.8.8.8/",
        "",
    ];
    for raw in denied {
        assert_unsafe(fetcher.fetch(Method::Get, raw).await, raw);
    }
}

#[tokio::test]
async fn names_resolving_to_non_public_are_denied_with_one_message() {
    let fetcher = strict();
    let names = [
        "http://loopback.test/", // 127.0.0.1 に解決
        "http://internal.test/", // 10.0.0.1 に解決
        "http://mixed.test/",    // 公開と非公開が混在 (1 つでも非公開なら拒否)
        "http://empty.test/",    // 解決結果が空
        "http://unknown.test/",  // 解決失敗
    ];
    for raw in names {
        assert_unsafe(fetcher.fetch(Method::Get, raw).await, raw);
    }

    // 内部アドレス・解決失敗・解決結果が空は同じ文面で、アドレスを含まない (S-9)。
    for raw in [
        "http://loopback.test/",
        "http://internal.test/",
        "http://empty.test/",
        "http://unknown.test/",
    ] {
        let err = fetcher.fetch(Method::Get, raw).await.unwrap_err();
        let message = err.to_string();
        assert_eq!(message, DENIED, "{raw}");
        assert!(!message.contains("127.0.0.1") && !message.contains("10.0.0.1"));
    }
}

// ---- S-1、S-4、S-7: 取得の基本 (ローカルサーバー) ----

#[tokio::test]
async fn fetch_basics_over_pinned_resolution() {
    let server = test_server::spawn().await;
    let fetcher = lenient(Limits::default());

    let ok = fetcher
        .fetch(Method::Get, &url_of(&server, "/ok"))
        .await
        .unwrap();
    assert_eq!(ok.status, 200);
    assert_eq!(ok.body, b"hello");
    assert_eq!(ok.final_url.path(), "/ok");
    // Content-Type を、そのまま (小文字化せず) 返す。ヘッダがなければ空文字列。
    assert_eq!(ok.content_type, "text/plain; charset=utf-8");
    let no_header = fetcher
        .fetch(Method::Get, &url_of(&server, "/chunked"))
        .await
        .unwrap();
    assert_eq!(no_header.content_type, "");
    // ヘッダが複数なら、すべてを ", " でつなぐ (S-11)
    let two = fetcher
        .fetch(Method::Get, &url_of(&server, "/two-content-types"))
        .await
        .unwrap();
    assert_eq!(two.content_type, "application/rss+xml, text/html");

    // Accept-Encoding: identity を送る (S-7)
    let echo = fetcher
        .fetch(Method::Get, &url_of(&server, "/echo-ae"))
        .await
        .unwrap();
    assert_eq!(echo.body, b"identity");

    // チャンク転送
    let chunked = fetcher
        .fetch(Method::Get, &url_of(&server, "/chunked"))
        .await
        .unwrap();
    assert_eq!(chunked.body, b"hello");

    // HEAD は本文なし
    let head = fetcher
        .fetch(Method::Head, &url_of(&server, "/ok"))
        .await
        .unwrap();
    assert_eq!(head.status, 200);
    assert!(head.body.is_empty());
}

#[tokio::test]
async fn denied_host_never_opens_a_connection() {
    let server = test_server::spawn().await;
    let url = format!("http://loopback.test:{}/ok", server.addr.port());

    assert_unsafe(strict().fetch(Method::Get, &url).await, &url);
    assert_eq!(server.accepted(), 0, "拒否した相手に接続してはいけない");
}

// ---- S-5: リダイレクト ----

#[tokio::test]
async fn redirects_are_followed_manually_and_rechecked_each_hop() {
    let server = test_server::spawn().await;
    let fetcher = lenient(Limits::default());

    // 公開 → 公開 は追従して成功する
    let public = fetcher
        .fetch(Method::Get, &url_of(&server, "/r-public"))
        .await
        .unwrap();
    assert_eq!(public.body, b"hello");
    assert_eq!(public.final_url.host_str(), Some("pub2.test"));

    // 相対 Location は Url::join で解決する
    let relative = fetcher
        .fetch(Method::Get, &url_of(&server, "/r-rel"))
        .await
        .unwrap();
    assert_eq!(relative.body, b"hello");

    // 遷移先が内部、内部に解決される名前、解釈が割れる Location、ループは拒否する
    for path in [
        "/r-10",
        "/r-meta",
        "/r-internal-name",
        "/r-backslash",
        "/r-loop",
    ] {
        let url = url_of(&server, path);
        assert_unsafe(fetcher.fetch(Method::Get, &url).await, &url);
    }

    // Location のない 3xx はそのまま返す
    let noloc = fetcher
        .fetch(Method::Get, &url_of(&server, "/r-noloc"))
        .await
        .unwrap();
    assert_eq!(noloc.status, 302);
}

// ---- S-6、S-7: 応答の上限と圧縮 ----

#[tokio::test]
async fn response_limits_and_encoding_are_enforced() {
    let server = test_server::spawn().await;
    let limits = Limits {
        max_bytes: 1024,
        request_timeout: Duration::from_secs(5),
        total_timeout: Duration::from_secs(1),
    };
    let fetcher = lenient(limits);
    // 拒否が遅れて固まるときも、テストが止まらず失敗として見えるようにする。
    let guard = Duration::from_secs(10);

    // 上限以内は成功する
    let ok = fetcher
        .fetch(Method::Get, &url_of(&server, "/ok"))
        .await
        .unwrap();
    assert_eq!(ok.body, b"hello");

    // 巨大な Content-Length の宣言は、本文を待たずに拒否する
    let declared = tokio::time::timeout(
        guard,
        fetcher.fetch(Method::Get, &url_of(&server, "/big-declared")),
    )
    .await
    .expect("本文を待って固まった: 早期に拒否されていない");
    assert_http(declared, "応答が大きすぎます");

    // 宣言なしで上限を超えてストリームされたら打ち切って拒否する
    let streamed = tokio::time::timeout(
        guard,
        fetcher.fetch(Method::Get, &url_of(&server, "/big-stream")),
    )
    .await
    .expect("固まった");
    assert_http(streamed, "応答が大きすぎます");

    // 遅く返し続ける応答は全体の締切で拒否する
    let slow = tokio::time::timeout(guard, fetcher.fetch(Method::Get, &url_of(&server, "/slow")))
        .await
        .expect("締切が効かず固まった");
    assert_http(slow, "応答に時間がかかりすぎています");

    // identity 以外の Content-Encoding は拒否する
    let gzip = fetcher.fetch(Method::Get, &url_of(&server, "/gzip")).await;
    assert_http(gzip, "未対応の圧縮形式です");

    // ヘッダが複数のときも全件を検査する (identity の後ろに gzip)
    let multi = fetcher
        .fetch(Method::Get, &url_of(&server, "/multi-encoding"))
        .await;
    assert_http(multi, "未対応の圧縮形式です");
}

// ---- S-8: プロキシ ----

/// テスト中だけ環境変数を設定し、失敗しても必ず戻す。
struct ProxyEnv;

impl ProxyEnv {
    fn set(value: &str) -> Self {
        // SAFETY: このテストだけが設定する。取得層は環境変数を読まないので他のテストに影響しない。
        unsafe {
            for key in ["HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"] {
                std::env::set_var(key, value);
            }
        }
        Self
    }
}

impl Drop for ProxyEnv {
    fn drop(&mut self) {
        // SAFETY: 上の set と同じ。
        unsafe {
            for key in ["HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"] {
                std::env::remove_var(key);
            }
        }
    }
}

#[tokio::test]
async fn proxy_environment_variables_are_ignored() {
    let server = test_server::spawn().await;
    let proxy = test_server::spawn().await;
    let _env = ProxyEnv::set(&format!("http://{}", proxy.addr));

    let fetcher = lenient(Limits::default());
    let fetched = fetcher
        .fetch(Method::Get, &url_of(&server, "/ok"))
        .await
        .unwrap();

    assert_eq!(fetched.body, b"hello");
    assert_eq!(proxy.accepted(), 0, "プロキシ経由で通信してはいけない");
}

// ---- S-4: ポート ----

#[tokio::test]
async fn ports_other_than_80_and_443_are_denied_even_for_public_addresses() {
    let fetcher = strict();
    for raw in [
        "http://8.8.8.8:8080/",
        "https://8.8.8.8:8443/",
        "http://8.8.8.8:22/",
    ] {
        let url = Url::parse(raw).unwrap();
        let result = fetcher.resolve_checked(&url).await;
        assert!(
            matches!(&result, Err(FeedError::UnsafeUrl(m)) if m == DENIED),
            "{raw}: 拒否されるはずが {result:?}"
        );
    }
}

#[tokio::test]
async fn ports_80_and_443_pass_the_port_check() {
    let fetcher = strict();
    for raw in [
        "http://8.8.8.8/",
        "http://8.8.8.8:80/",
        "https://8.8.8.8/",
        "https://8.8.8.8:443/",
    ] {
        let url = Url::parse(raw).unwrap();
        assert!(
            fetcher.resolve_checked(&url).await.is_ok(),
            "許可されるはず: {raw}"
        );
    }
}

// ---- S-3、S-4: IDN は名前解決とアドレス固定まで通る ----

#[tokio::test]
async fn idn_host_is_resolved_and_pinned() {
    let server = test_server::spawn().await;
    // 名前解決には punycode 化された名前が渡される
    let puny = Url::parse("http://例え.jp/")
        .unwrap()
        .host_str()
        .unwrap()
        .to_string();
    let lookup = FakeLookup::new().with(&puny, vec![ip("127.0.0.1")]);
    let fetcher = SafeFetcher::for_test(lookup, vec![ip("127.0.0.1")], Limits::default());

    let url = format!("http://例え.jp:{}/ok", server.addr.port());
    let fetched = fetcher.fetch(Method::Get, &url).await.unwrap();
    assert_eq!(fetched.body, b"hello");
}

// ---- S-6: 名前解決も通算の締切に含める ----

#[tokio::test]
async fn lookup_that_never_returns_is_cut_off_by_the_deadline() {
    let limits = Limits {
        max_bytes: 1024,
        request_timeout: Duration::from_secs(5),
        total_timeout: Duration::from_secs(1),
    };
    let fetcher = SafeFetcher::for_test(StuckLookup, vec![], limits);

    let result = tokio::time::timeout(
        Duration::from_secs(5),
        fetcher.fetch(Method::Get, "http://stuck.test/"),
    )
    .await
    .expect("名前解決の締切が効かず固まった");
    let err = result.unwrap_err();
    assert!(matches!(err, FeedError::UnsafeUrl(_)), "{err:?}");
    assert_eq!(err.to_string(), DENIED);
}

// ---- S-10: 本番の入口 (実際の名前解決) ----

#[tokio::test]
async fn production_fetcher_denies_localhost_via_real_resolution() {
    // OS の名前解決は localhost だけを使う (外部ネットワークに依存しない)。
    let resolved = SystemLookup.lookup("localhost").await.unwrap();
    assert!(!resolved.is_empty());
    assert!(resolved.iter().all(|a| a.is_loopback()), "{resolved:?}");

    // 本番用のコンストラクタは許可アドレスを持たず、ループバックを拒否する。
    let result = SafeFetcher::new()
        .fetch(Method::Get, "http://localhost/")
        .await;
    assert_unsafe(result, "http://localhost/");
}

// ---- 定数 (S-5、S-6) ----

#[test]
fn constants_match_the_spec() {
    let limits = Limits::default();
    assert_eq!(limits.max_bytes, 2 * 1024 * 1024);
    assert_eq!(limits.request_timeout, Duration::from_secs(30));
    assert_eq!(limits.total_timeout, Duration::from_secs(45));
    assert_eq!(MAX_REDIRECTS, 5);
}
