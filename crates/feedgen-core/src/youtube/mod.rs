//! YouTube の検索 URL を、YouTube Data API の検索で動画のフィードにする (docs/specs/youtube.md)。

use chrono::{DateTime, FixedOffset};

use crate::error::{FeedError, Result};
use crate::models::RssFeed;

pub(crate) const SEARCH_ENDPOINT: &str = "https://www.googleapis.com/youtube/v3/search";

pub(crate) fn search_query(_url: &str) -> Option<String> {
    todo!()
}

pub(crate) fn api_url(_endpoint: &str, _query: &str, _max_items: usize, _key: &str) -> String {
    todo!()
}

pub(crate) fn feed_from_response(
    _status: u16,
    _body: &[u8],
    _query: &str,
    _input_url: &str,
    _max_items: usize,
    _now: DateTime<FixedOffset>,
) -> Result<RssFeed> {
    let _ = FeedError::YouTube(String::new());
    todo!()
}

#[cfg(test)]
mod tests;
