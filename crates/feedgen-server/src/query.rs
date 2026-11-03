//! `/feed` のクエリの解析と検証 (api.md A-2、A-4)。

use axum::http::StatusCode;
use feedgen_core::generator::GenerateOptions;

/// 検証済みのリクエスト。
#[derive(Debug)]
pub struct FeedRequest {
    pub url: String,
    pub options: GenerateOptions,
}

/// 検証の失敗。`detail` がそのまま `{"detail": …}` の本文になる。
#[derive(Debug, PartialEq, Eq)]
pub struct ApiError {
    pub status: StatusCode,
    pub detail: String,
}

/// クエリの (名前, 値) の組から、検証済みのリクエストを作る。
pub fn parse_feed_query(pairs: &[(String, String)]) -> Result<FeedRequest, ApiError> {
    let _ = pairs;
    todo!("api.md A-2")
}
