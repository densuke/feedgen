//! YouTube の検索 URL を、YouTube Data API の検索で動画のフィードにする (docs/specs/youtube.md)。
//!
//! 取得先のホストは固定 (`SEARCH_ENDPOINT`) で、入力に由来しない。取得は既存の `SafeFetcher` を通す。

use chrono::{DateTime, FixedOffset};
use scraper::Html;
use serde_json::Value;
use url::Url;

use crate::error::{FeedError, Result};
use crate::models::{RssFeed, RssItem};

/// API の検索の取得先 (Y-3)。本番はこの値だけを使う。
pub(crate) const SEARCH_ENDPOINT: &str = "https://www.googleapis.com/youtube/v3/search";

const DESCRIPTION_LIMIT: usize = 300;
pub(crate) const NO_KEY: &str = "YouTube の検索には API キーの設定が必要です";

/// YouTube の検索 URL なら、検索語を返す (Y-1)。
pub(crate) fn search_query(url: &str) -> Option<String> {
    let url = Url::parse(url).ok()?;
    let is_target = matches!(url.scheme(), "http" | "https")
        && url.host_str() == Some("www.youtube.com")
        && url.port().is_none()
        && url.path() == "/results";
    if !is_target {
        return None;
    }
    url.query_pairs()
        .find(|(name, _)| name == "search_query")
        .map(|(_, value)| value.into_owned())
        .filter(|value| !value.trim().is_empty())
}

/// API の検索の URL (Y-3)。`maxResults` は 1〜50 に丸める。
pub(crate) fn api_url(endpoint: &str, query: &str, max_items: usize, key: &str) -> String {
    let max_results = max_items.clamp(1, 50).to_string();
    let mut url = Url::parse(endpoint).expect("取得先の定数が URL として不正");
    url.query_pairs_mut()
        .append_pair("part", "snippet")
        .append_pair("type", "video")
        .append_pair("order", "relevance")
        .append_pair("maxResults", &max_results)
        .append_pair("q", query)
        .append_pair("key", key);
    url.into()
}

/// API の応答をフィードにする (Y-4、Y-5、Y-7)。
pub(crate) fn feed_from_response(
    status: u16,
    body: &[u8],
    query: &str,
    input_url: &str,
    max_items: usize,
    now: DateTime<FixedOffset>,
) -> Result<RssFeed> {
    let json: Option<Value> = serde_json::from_slice(body).ok();
    if status != 200 {
        return Err(api_error(status, json.as_ref()));
    }
    let Some(items) = json.as_ref().and_then(|j| j["items"].as_array()) else {
        return Err(api_error(status, None));
    };
    Ok(RssFeed {
        title: format!("YouTube検索: {query}"),
        description: format!("YouTube検索「{query}」の結果"),
        link: input_url.to_string(),
        items: items
            .iter()
            .filter_map(|item| article(item, now))
            .take(max_items)
            .collect(),
    })
}

fn article(item: &Value, now: DateTime<FixedOffset>) -> Option<RssItem> {
    let id = item["id"]["videoId"].as_str()?;
    let snippet = &item["snippet"];
    let text = |name: &str| snippet[name].as_str().map(decode).unwrap_or_default();

    let title = text("title");
    let mut description = text("description");
    if description.chars().count() > DESCRIPTION_LIMIT {
        description = description
            .chars()
            .take(DESCRIPTION_LIMIT)
            .collect::<String>()
            + "...";
    }
    let channel = text("channelTitle");
    if !channel.is_empty() {
        description = if description.is_empty() {
            format!("チャンネル: {channel}")
        } else {
            format!("チャンネル: {channel}\n\n{description}")
        };
    }
    let pub_date = snippet["publishedAt"]
        .as_str()
        .and_then(|at| DateTime::parse_from_rfc3339(at).ok())
        .unwrap_or(now);
    Some(RssItem {
        title: if title.is_empty() {
            "無題".to_string()
        } else {
            title
        },
        description,
        link: format!("https://www.youtube.com/watch?v={id}"),
        pub_date: Some(pub_date),
        guid: Some(format!("youtube-video-{id}")),
    })
}

/// API の文字列に含まれる HTML の文字参照 (`&amp;` など) を復号する (Y-4)。
fn decode(text: &str) -> String {
    Html::parse_fragment(text).root_element().text().collect()
}

/// 失敗の文言。キーも、応答の本文も含めない (Y-7)。
fn api_error(status: u16, json: Option<&Value>) -> FeedError {
    let error = json.map(|j| &j["error"]);
    let reasons: Vec<&str> = ["errors", "details"]
        .iter()
        .filter_map(|list| error.and_then(|e| e[list].as_array()))
        .flatten()
        .filter_map(|entry| entry["reason"].as_str())
        .collect();
    let message = if reasons.contains(&"quotaExceeded") {
        "YouTube API のクォータを超過しました".to_string()
    } else if reasons.contains(&"keyInvalid") || reasons.contains(&"API_KEY_INVALID") {
        "YouTube API キーが無効です".to_string()
    } else {
        format!("YouTube API の呼び出しに失敗しました (HTTP {status})")
    };
    FeedError::YouTube(message)
}

#[cfg(test)]
mod tests;
