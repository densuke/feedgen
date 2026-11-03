//! HTML の `<link rel="alternate">` からのフィード検出 (docs/specs/detector.md D-1、D-2)。

use std::collections::HashSet;

use scraper::ElementRef;
use url::Url;

use super::{FeedInfo, kind_from_media_type};
use crate::parser::parse_document;

/// `type` に含まれていればフィードとみなす MIME タイプ (小文字)。
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
    let document = parse_document(html);
    let mut seen = HashSet::new();
    document
        .tree
        .root()
        .descendants()
        .filter_map(ElementRef::wrap)
        .filter(|element| element.value().name() == "link")
        .filter_map(|link| feed_from_link(link, &base))
        .filter(|feed| seen.insert(feed.url.clone()))
        .collect()
}

fn feed_from_link(link: ElementRef, base: &Url) -> Option<FeedInfo> {
    let value = link.value();
    let is_alternate = value
        .attr("rel")?
        .split_ascii_whitespace()
        .any(|token| token.eq_ignore_ascii_case("alternate"));
    if !is_alternate {
        return None;
    }

    let media_type = value.attr("type")?.to_ascii_lowercase();
    if !FEED_TYPES.iter().any(|known| media_type.contains(known)) {
        return None;
    }

    let href = value.attr("href")?.trim();
    if href.is_empty() {
        return None;
    }
    let url = base.join(href).ok()?;
    if !matches!(url.scheme(), "http" | "https") {
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
