//! HTML パーサ (docs/specs/parser.md)。
//!
//! RED 段階のスタブ。実装は仕様 P-1〜P-7 に従って後続のコミットで書く。

use chrono::{DateTime, FixedOffset};

use crate::models::RssItem;

/// ページのメタデータ。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Metadata {
    pub title: String,
    pub description: String,
    pub link: String,
}

/// HTML からメタデータと記事一覧を取り出す。通信も時計の読み取りもしない (G-4)。
pub fn parse(
    _html: &str,
    _base_url: &str,
    _max_items: usize,
    _now: DateTime<FixedOffset>,
) -> (Metadata, Vec<RssItem>) {
    todo!("P-1〜P-6")
}

#[cfg(test)]
mod tests;
