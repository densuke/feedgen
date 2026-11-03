//! 記事・フィードの型と、RSS 2.0 への書き出し (docs/specs/models.md)。
//!
//! RED 段階のスタブ。実装は仕様 M-1〜M-10 に従って後続のコミットで書く。

use chrono::{DateTime, FixedOffset};

/// RSS の記事 1 件。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RssItem {
    pub title: String,
    pub description: String,
    pub link: String,
    pub pub_date: Option<DateTime<FixedOffset>>,
    pub guid: Option<String>,
}

/// RSS のフィード (チャンネル + 記事)。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RssFeed {
    pub title: String,
    pub description: String,
    pub link: String,
    pub items: Vec<RssItem>,
}

impl RssFeed {
    /// RSS 2.0 の XML 文字列にする (M-2)。`now` は `lastBuildDate` の代わりに使う現在時刻。
    pub fn to_xml(&self, _now: DateTime<FixedOffset>) -> String {
        todo!("M-2〜M-9")
    }
}

#[cfg(test)]
mod tests;
