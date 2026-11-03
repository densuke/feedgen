//! HTML の `<link rel="alternate">` からのフィード検出 (docs/specs/detector.md D-1、D-2)。

use std::collections::HashSet;

use scraper::ElementRef;
use url::Url;

use super::{FeedInfo, kind_from_media_type};
use crate::parser::parse_document;

/// `<link>` の `type` が、これと完全一致すればフィードとみなす MIME タイプ (media type。小文字)。
const FEED_TYPES: [&str; 6] = [
    "application/rss+xml",
    "application/atom+xml",
    "application/xml",
    "text/xml",
    "application/json",
    "application/feed+json",
];

/// `title` がないときの既定。Python 版と同じ。
const DEFAULT_TITLE: &str = "不明なフィード";

/// 取得済みの HTML から、フィードの候補を文書順に返す。同じ URL は最初の 1 件だけ残す。
pub(super) fn detect_from_html(html: &str, base_url: &str) -> Vec<FeedInfo> {
    let Ok(base) = Url::parse(base_url) else {
        return Vec::new();
    };
    // ページ自身 (fragment を除く)。これを指す href は捨てる。
    let mut page = base.clone();
    page.set_fragment(None);
    let document = parse_document(html);
    let mut seen = HashSet::new();
    document
        .tree
        .root()
        .descendants()
        .filter_map(ElementRef::wrap)
        .filter(|element| element.value().name() == "link")
        .filter_map(|link| feed_from_link(link, &base, &page))
        .filter(|feed| seen.insert(feed.url.clone()))
        .collect()
}

fn feed_from_link(link: ElementRef, base: &Url, page: &Url) -> Option<FeedInfo> {
    let value = link.value();
    let is_alternate = value
        .attr("rel")?
        .split_ascii_whitespace()
        .any(|token| token.eq_ignore_ascii_case("alternate"));
    if !is_alternate {
        return None;
    }

    let media_type = media_type(value.attr("type")?);
    if !FEED_TYPES.contains(&media_type.as_str()) {
        return None;
    }

    // HTML の URL の扱いに合わせ、ASCII の空白だけを除く (NBSP などは除かない)。
    let href = value
        .attr("href")?
        .trim_matches(|c: char| c.is_ascii_whitespace());
    if href.is_empty() {
        return None;
    }
    let mut url = base.join(href).ok()?;
    if !matches!(url.scheme(), "http" | "https") {
        return None;
    }
    // 認証部 (ユーザー名・パスワード) つきは、結果に残さない。
    if !url.username().is_empty() || url.password().is_some() {
        return None;
    }
    url.set_fragment(None);
    if url == *page {
        return None;
    }

    let title = value
        .attr("title")
        .map(str::trim)
        .filter(|title| !title.is_empty())
        .unwrap_or(DEFAULT_TITLE);
    Some(FeedInfo {
        url: url.to_string(),
        title: title.to_string(),
        kind: kind_from_media_type(&media_type),
    })
}

/// `Content-Type` や `type` の値から、media type だけを取り出す。パラメータ (`;` 以降) と前後の空白を除き、
/// ASCII の小文字にする。
pub(super) fn media_type(value: &str) -> String {
    value
        .split(';')
        .next()
        .unwrap_or("")
        .trim()
        .to_ascii_lowercase()
}
