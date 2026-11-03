//! 既存フィードの検出 (docs/specs/detector.md)。
//!
//! RED 段階のスタブ。実装は仕様 D-1〜D-7 に従って後続のコミットで書く。

use crate::fetch::{Lookup, SafeFetcher};

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
pub const PROBE_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(10);

/// 取得済みの HTML の `<link rel="alternate">` から、フィードの候補を取り出す (D-1、D-2)。
pub fn detect_from_html(_html: &str, _base_url: &str) -> Vec<FeedInfo> {
    todo!("D-1, D-2")
}

/// サイトのルートにある共通パスを並列に `HEAD` で確かめる (D-3、D-4)。
pub async fn probe_common_paths<L: Lookup>(
    fetcher: &SafeFetcher<L>,
    base_url: &str,
) -> Option<FeedInfo> {
    probe_common_paths_with(fetcher, base_url, PROBE_TIMEOUT).await
}

/// `probe_common_paths` の、1 本ごとの締切を差し替えられる版 (テスト用)。
pub(crate) async fn probe_common_paths_with<L: Lookup>(
    _fetcher: &SafeFetcher<L>,
    _base_url: &str,
    _probe_timeout: std::time::Duration,
) -> Option<FeedInfo> {
    todo!("D-3, D-4")
}

/// 本文のルート要素が、フィードのものかを判定する (D-5)。
pub fn feed_root(_body: &[u8]) -> Option<RootKind> {
    todo!("D-5")
}

/// 代理取得で返す `Content-Type` (D-6)。`original` に `charset` があれば引き継ぐ。
pub fn proxied_content_type(_root: RootKind, _original: &str) -> String {
    todo!("D-6")
}

#[cfg(test)]
mod probe_server;
#[cfg(test)]
mod tests;
