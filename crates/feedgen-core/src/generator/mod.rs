//! フィード生成のパイプライン (docs/specs/pipeline.md)。
//!
//! RED 段階のスタブ。実装は仕様 G-1〜G-11 に従って後続のコミットで書く。

use chrono::{DateTime, FixedOffset};

use crate::detector::FeedInfo;
use crate::error::Result;
use crate::fetch::{Lookup, SafeFetcher, SystemLookup};
use crate::models::RssFeed;

/// `generate` のオプション (G-1)。`max_items` の範囲 (1〜100) の検証は、API 層で行う。
#[derive(Debug, Clone)]
pub struct GenerateOptions {
    pub max_items: usize,
    pub user_agent: String,
    pub use_feed: bool,
    pub feed_first: bool,
}

impl Default for GenerateOptions {
    fn default() -> Self {
        Self {
            max_items: 20,
            user_agent: "feedgen/1.0".to_string(),
            use_feed: false,
            feed_first: false,
        }
    }
}

/// `generate` の結果 (G-1)。
#[derive(Debug)]
pub enum Outcome {
    /// HTML を解析して生成したフィード。`detected` は、`feed_first` のときの検出結果。
    Generated {
        feed: RssFeed,
        detected: Vec<FeedInfo>,
    },
    /// 既存のフィードを、そのまま返す。本文はバイト列のまま変換しない。
    Proxied {
        body: Vec<u8>,
        content_type: String,
        source_url: String,
    },
}

/// フィード生成のパイプライン。`SafeFetcher` を 1 つ持つ。
pub struct FeedGenerator<L: Lookup = SystemLookup> {
    #[allow(dead_code)]
    fetcher: SafeFetcher<L>,
}

impl FeedGenerator<SystemLookup> {
    /// 本番用。
    pub fn new() -> Self {
        Self {
            fetcher: SafeFetcher::new(),
        }
    }
}

impl Default for FeedGenerator<SystemLookup> {
    fn default() -> Self {
        Self::new()
    }
}

impl<L: Lookup> FeedGenerator<L> {
    /// テスト用の差し込み口。
    #[cfg(test)]
    pub(crate) fn with_fetcher(fetcher: SafeFetcher<L>) -> Self {
        Self { fetcher }
    }

    /// URL からフィードを生成する (G-1、G-2)。現在時刻は、引数で受け取る (G-4)。
    pub async fn generate(
        &self,
        _url: &str,
        _options: &GenerateOptions,
        _now: DateTime<FixedOffset>,
    ) -> Result<Outcome> {
        todo!("G-1〜G-11")
    }
}

#[cfg(test)]
mod tests;
