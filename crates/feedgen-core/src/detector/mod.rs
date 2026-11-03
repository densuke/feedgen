//! 既存フィードの検出 (docs/specs/detector.md)。
//!
//! - HTML の `<link rel="alternate">` から候補を取り出す (`detect_from_html`)。
//! - 候補がなければ、サイトのルートの共通パスを並列に `HEAD` で確かめる (`probe_common_paths`)。
//! - 取得した本文が、フィードそのものかを、ルート要素で判定する (`feed_root`)。
//!
//! 通信は `probe_common_paths` だけで、すべて取得層 (`SafeFetcher`) を通す。

mod html;
mod root;

use std::time::Duration;

use futures_util::future::join_all;
use url::Url;

use crate::fetch::{Fetched, Lookup, Method, SafeFetcher};

/// 検出したフィードの種類。`label` が `X-Existing-Feed-Type` などに出る名前。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FeedKind {
    Rss,
    Atom,
    Json,
    Xml,
}

impl FeedKind {
    /// 表示用の名前 (Python 版と同じ)。
    pub fn label(self) -> &'static str {
        match self {
            FeedKind::Rss => "RSS",
            FeedKind::Atom => "Atom",
            FeedKind::Json => "JSON",
            FeedKind::Xml => "XML",
        }
    }
}

/// 検出したフィードの候補。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FeedInfo {
    pub url: String,
    pub title: String,
    pub kind: FeedKind,
}

/// 本文のルート要素から判定したフィードの種類 (D-5)。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RootKind {
    /// `<rss>` (RSS 0.9x / 2.0)
    Rss,
    /// `<rdf:RDF>` (RSS 1.0)
    Rdf,
    /// `<feed>` (Atom)
    Atom,
}

/// 共通パスの確認で、1 本ごとに付ける締切 (D-3)。
pub const PROBE_TIMEOUT: Duration = Duration::from_secs(10);

/// 共通パス。この順序が優先順位 (D-3)。
const COMMON_PATHS: [&str; 8] = [
    "/feed",
    "/rss",
    "/atom.xml",
    "/rss.xml",
    "/feed.xml",
    "/feeds/all.atom.xml",
    "/rss/index.xml",
    "/feed/index.xml",
];

/// 取得済みの HTML の `<link rel="alternate">` から、フィードの候補を取り出す (D-1、D-2)。
pub fn detect_from_html(html: &str, base_url: &str) -> Vec<FeedInfo> {
    html::detect_from_html(html, base_url)
}

/// 本文のルート要素が、フィードのものかを判定する (D-5)。
pub fn feed_root(body: &[u8]) -> Option<RootKind> {
    root::feed_root(body)
}

/// 代理取得で返す `Content-Type` (D-6)。`original` に `charset` があれば引き継ぐ。
pub fn proxied_content_type(root: RootKind, original: &str) -> String {
    root::proxied_content_type(root, original)
}

/// サイトのルートにある共通パスを並列に `HEAD` で確かめる (D-3、D-4)。
pub async fn probe_common_paths<L: Lookup>(
    fetcher: &SafeFetcher<L>,
    base_url: &str,
    user_agent: &str,
) -> Option<FeedInfo> {
    probe_common_paths_with(fetcher, base_url, user_agent, PROBE_TIMEOUT).await
}

/// `probe_common_paths` の、1 本ごとの締切を差し替えられる版 (テスト用)。
pub(crate) async fn probe_common_paths_with<L: Lookup>(
    fetcher: &SafeFetcher<L>,
    base_url: &str,
    user_agent: &str,
    probe_timeout: Duration,
) -> Option<FeedInfo> {
    let base = Url::parse(base_url).ok()?;
    let host = base.host_str()?;
    let netloc = match base.port() {
        Some(port) => format!("{host}:{port}"),
        None => host.to_string(),
    };
    let netloc = netloc.as_str();
    let origin = format!("{}://{netloc}", base.scheme());
    let origin = origin.as_str();

    let probes = COMMON_PATHS.iter().map(move |path| async move {
        let url = format!("{origin}{path}");
        // 締切、取得層の拒否、通信エラーは、いずれも「ない」(エラーは返さない)。
        let response = tokio::time::timeout(
            probe_timeout,
            fetcher.fetch_as(Method::Head, &url, user_agent),
        )
        .await
        .ok()?
        .ok()?;
        let kind = probe_kind(&response, path)?;
        Some(FeedInfo {
            title: format!("{netloc} - {}", kind.label()),
            url,
            kind,
        })
    });
    // `join_all` は順序を保つ。優先順位の最も高い 1 件を返す。
    join_all(probes).await.into_iter().flatten().next()
}

/// 共通パスの応答がフィードなら、その種類 (D-3 の「ある」、D-4)。
fn probe_kind(response: &Fetched, path: &str) -> Option<FeedKind> {
    if response.status != 200 {
        return None;
    }
    // パラメータは見ない (`application/octet-stream; filename=feed.xml` をフィードとみなさない)。
    let media_type = html::media_type(&response.content_type);
    // 緩い判定 (`application/rdf+xml` なども通す)。誤検出は、本文のルート要素の判定 (D-5) で弾く。
    let feed_like = ["rss", "atom", "xml", "json"]
        .iter()
        .any(|word| media_type.contains(word));
    // `application/xhtml+xml` は `xml` を含むので、`html` を含むものは除く。
    if !feed_like || media_type.contains("html") {
        return None;
    }
    match kind_from_media_type(&media_type) {
        // `application/xml` などは、パスで補う。
        FeedKind::Xml => Some(kind_from_path(path)),
        kind => Some(kind),
    }
}

/// MIME タイプから種類を決める。`rss`、`atom`、`json` の順に見る。
fn kind_from_media_type(media_type: &str) -> FeedKind {
    if media_type.contains("rss") {
        FeedKind::Rss
    } else if media_type.contains("atom") {
        FeedKind::Atom
    } else if media_type.contains("json") {
        FeedKind::Json
    } else {
        FeedKind::Xml
    }
}

fn kind_from_path(path: &str) -> FeedKind {
    if path.contains("atom") {
        FeedKind::Atom
    } else if path.contains("json") {
        FeedKind::Json
    } else {
        FeedKind::Rss
    }
}

#[cfg(test)]
pub(crate) mod probe_server;
#[cfg(test)]
mod tests;
