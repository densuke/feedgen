//! フィード生成のパイプライン (docs/specs/pipeline.md)。
//!
//! 処理の順序 (G-2): 対象の URL を 1 回だけ取得し、フィードそのものならそのまま返し、HTML なら、
//! (フラグがあれば) 既存フィードを検出して代理取得し、できなければ HTML を解析して生成する。
//! 現在時刻は呼び出し側から受け取り、このモジュールは時計を読まない (G-4)。

use chrono::{DateTime, FixedOffset};

use crate::charset::decode_html;
use crate::detector::{
    FeedInfo, detect_from_html, feed_root, probe_common_paths, proxied_content_type,
};
use crate::error::{FeedError, Result};
use crate::fetch::{Fetched, Lookup, Method, SafeFetcher, SystemLookup};
use crate::models::RssFeed;
use crate::parser::parse;

/// 代理取得のために試す、検出した候補の最大数 (G-2 の 6)。1 つのページが `<link>` を大量に並べても、
/// 取得が増幅しないようにする。
const MAX_FEED_CANDIDATES: usize = 3;

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

/// `user_agent` が、ヘッダにそのまま入れられる値か確かめる (api.md A-2)。
/// 可視 ASCII (U+0020〜U+007E) のみ、1〜256 文字。違反は理由の文字列。
pub fn validate_user_agent(user_agent: &str) -> std::result::Result<(), String> {
    let _ = user_agent;
    todo!("api.md A-2")
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
        url: &str,
        options: &GenerateOptions,
        now: DateTime<FixedOffset>,
    ) -> Result<Outcome> {
        let user_agent = options.user_agent.as_str();

        // 1. 対象の URL を、1 回だけ取得する。以後、この本文を使い回す。
        let page = self.fetcher.fetch_as(Method::Get, url, user_agent).await?;
        require_ok(&page)?;

        // 3. URL 自体がフィードなら、フラグにかかわらず、そのまま返す (G-7)。
        if let Some(root) = feed_root(&page.body) {
            return Ok(Outcome::Proxied {
                content_type: proxied_content_type(root, &page.content_type),
                source_url: page.final_url.to_string(),
                body: page.body,
            });
        }

        // 4. HTML を文字列にする (G-9)。
        let html = decode_html(&page.body, &page.content_type);

        // 5〜7. 既存フィードの検出と代理取得 (G-2、G-11)。失敗は、HTML の解析に進む。
        let mut detected = Vec::new();
        if options.use_feed || options.feed_first {
            detected = self
                .detect(&html, page.final_url.as_str(), user_agent)
                .await;
            if options.use_feed
                && let Some(proxied) = self.proxy_candidates(&detected, user_agent).await
            {
                return Ok(proxied);
            }
        }

        // 8. HTML を解析して生成する。基準 URL は、渡された URL (guid を変えないため。G-2)。
        let (metadata, items) = parse(&html, url, options.max_items, now);
        Ok(Outcome::Generated {
            feed: RssFeed {
                title: metadata.title,
                description: metadata.description,
                link: metadata.link,
                items,
            },
            detected: if options.feed_first {
                detected
            } else {
                Vec::new()
            },
        })
    }

    /// HTML の `<link>` から候補を探し、なければ共通パスを確かめる。基準は最終 URL (G-2)。
    async fn detect(&self, html: &str, final_url: &str, user_agent: &str) -> Vec<FeedInfo> {
        let mut found = detect_from_html(html, final_url);
        if found.is_empty()
            && let Some(info) = probe_common_paths(&self.fetcher, final_url, user_agent).await
        {
            found.push(info);
        }
        found
    }

    /// 候補を先頭から順に、最大 `MAX_FEED_CANDIDATES` 件まで取得し、最初に使えたものを `Proxied` にする。
    /// 1 件も使えなければ `None` (G-2 の 6、7)。
    async fn proxy_candidates(&self, detected: &[FeedInfo], user_agent: &str) -> Option<Outcome> {
        for candidate in detected.iter().take(MAX_FEED_CANDIDATES) {
            if let Some(outcome) = self.fetch_feed(candidate, user_agent).await {
                return Some(outcome);
            }
        }
        None
    }

    /// 候補を取得し、ステータスが 200 で、本文のルート要素がフィードなら `Proxied` にする。
    async fn fetch_feed(&self, candidate: &FeedInfo, user_agent: &str) -> Option<Outcome> {
        let feed = self
            .fetcher
            .fetch_as(Method::Get, &candidate.url, user_agent)
            .await
            .ok()?;
        if feed.status != 200 {
            return None;
        }
        let root = feed_root(&feed.body)?;
        Some(Outcome::Proxied {
            content_type: proxied_content_type(root, &feed.content_type),
            source_url: candidate.url.clone(),
            body: feed.body,
        })
    }
}

/// ステータスが 200 のときだけ成功とする (G-8)。
fn require_ok(page: &Fetched) -> Result<()> {
    if page.status == 200 {
        Ok(())
    } else {
        Err(FeedError::Http(format!(
            "取得先が内容を返しませんでした (HTTP {})",
            page.status
        )))
    }
}

#[cfg(test)]
mod tests;
