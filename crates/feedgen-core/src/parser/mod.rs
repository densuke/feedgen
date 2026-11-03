//! HTML パーサ (docs/specs/parser.md)。
//!
//! HTML5 準拠の `scraper` で 1 回だけ解析し、メタデータと記事の抽出に同じ木を使う (P-1)。
//! 通信も時計の読み取りもしない。現在時刻は引数で受け取る (G-4、P-5)。

mod link;
mod strategies;
mod text;

use std::collections::HashSet;

use chrono::{DateTime, FixedOffset};
use html5ever::driver::{self, ParseOpts};
use html5ever::tendril::TendrilSink;
use html5ever::tree_builder::TreeBuilderOpts;
use scraper::{Html, HtmlTreeSink};

use crate::models::RssItem;
use strategies::Strategies;
use text::{cut, selector, text_of};

/// ページのメタデータ。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Metadata {
    pub title: String,
    pub description: String,
    pub link: String,
}

/// HTML からメタデータと記事一覧を取り出す。
///
/// 壊れた HTML でも失敗しない (Python 版の `html.parser` と同じく `Result` を返さない)。
pub fn parse(
    html: &str,
    base_url: &str,
    max_items: usize,
    now: DateTime<FixedOffset>,
) -> (Metadata, Vec<RssItem>) {
    let document = parse_document(html);
    let metadata = metadata(&document, base_url);

    let strategies = Strategies {
        document: &document,
        base_url,
        now,
    };
    let mut items = strategies.headings(max_items);
    if items.len() < max_items {
        items.extend(strategies.cards(max_items - items.len()));
    }
    if items.len() < max_items {
        items.extend(strategies.blocks(max_items - items.len()));
    }
    (metadata, deduplicate(items, max_items))
}

/// スクリプト無効で解析する (P-1)。
///
/// `scraper::Html::parse_document` は既定のオプション (スクリプト有効) で解析し、`<noscript>` の中身を
/// 生の文字列にしてしまう。無効にすると、中身が通常の要素として解析される (Python 版と同じ)。
pub(crate) fn parse_document(html: &str) -> Html {
    let options = ParseOpts {
        tree_builder: TreeBuilderOpts {
            scripting_enabled: false,
            ..Default::default()
        },
        ..Default::default()
    };
    driver::parse_document(HtmlTreeSink::new(Html::new_document()), options).one(html)
}

/// タイトルと説明 (P-3)。
fn metadata(document: &Html, base_url: &str) -> Metadata {
    // `<title>` 要素がないときだけ「無題」。空の要素は空のまま。
    let title = document
        .select(&selector("title"))
        .next()
        .map_or_else(|| "無題".to_string(), |t| text_of(t).trim().to_string());

    // `<meta name="description">` の content が空でなければそれ。なければ最初の `<p>`。
    let meta_content = document
        .select(&selector(r#"meta[name="description"]"#))
        .next()
        .and_then(|meta| meta.value().attr("content"))
        .filter(|content| !content.is_empty());
    let description = match meta_content {
        Some(content) => content.trim().to_string(),
        None => document
            .select(&selector("p"))
            .next()
            .map(|p| cut(text_of(p).trim(), 200))
            .unwrap_or_default(),
    };

    Metadata {
        title,
        description,
        link: base_url.to_string(),
    }
}

/// タイトル (前後の空白を除き小文字にしたもの) が同じ記事は、最初の 1 件だけ残す。
/// タイトルが空の記事は捨てる。最後に `max_items` 件に切る。
fn deduplicate(items: Vec<RssItem>, max_items: usize) -> Vec<RssItem> {
    let mut seen = HashSet::new();
    items
        .into_iter()
        .filter(|item| {
            let key = item.title.trim().to_lowercase();
            !key.is_empty() && seen.insert(key)
        })
        .take(max_items)
        .collect()
}

#[cfg(test)]
mod tests;
