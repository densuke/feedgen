//! `/feed` のクエリの解析と検証 (api.md A-2、A-4)。

use axum::http::StatusCode;
use feedgen_core::generator::{GenerateOptions, validate_user_agent};

const MAX_URL_CHARS: usize = 2048;
const DEFAULT_USER_AGENT: &str = "feedgen-api/1.0";

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

impl ApiError {
    fn new(status: StatusCode, detail: impl Into<String>) -> Self {
        Self {
            status,
            detail: detail.into(),
        }
    }

    fn invalid(detail: impl Into<String>) -> Self {
        Self::new(StatusCode::UNPROCESSABLE_ENTITY, detail)
    }
}

/// クエリの (名前, 値) の組から、検証済みのリクエストを作る。同じ名前は先頭の値を使う。
pub fn parse_feed_query(pairs: &[(String, String)]) -> Result<FeedRequest, ApiError> {
    let value = |name: &str| {
        pairs
            .iter()
            .find(|(key, _)| key == name)
            .map(|(_, value)| value.as_str())
    };

    let url = value("url").ok_or_else(|| ApiError::invalid("url は必須です"))?;
    if url.chars().count() > MAX_URL_CHARS {
        return Err(ApiError::new(
            StatusCode::BAD_REQUEST,
            format!("url は {MAX_URL_CHARS} 文字以内で指定してください"),
        ));
    }

    let max_items = match value("max_items") {
        None => GenerateOptions::default().max_items,
        Some(raw) => raw
            .parse::<usize>()
            .ok()
            .filter(|n| (1..=100).contains(n))
            .ok_or_else(|| ApiError::invalid("max_items は 1〜100 の整数で指定してください"))?,
    };
    let use_feed = flag(value("use_feed"), "use_feed")?;
    let feed_first = flag(value("feed_first"), "feed_first")?;

    for feature in ["decode_google_news", "translate"] {
        if parse_bool(value(feature).unwrap_or("false")) == Some(true) {
            return Err(ApiError::new(
                StatusCode::BAD_REQUEST,
                format!("この機能は未対応です ({feature})"),
            ));
        }
    }

    let user_agent = value("user_agent").unwrap_or(DEFAULT_USER_AGENT);
    validate_user_agent(user_agent)
        .map_err(|reason| ApiError::new(StatusCode::BAD_REQUEST, reason))?;

    Ok(FeedRequest {
        url: url.to_string(),
        options: GenerateOptions {
            max_items,
            user_agent: user_agent.to_string(),
            use_feed,
            feed_first,
        },
    })
}

/// 真偽値のパラメータ。なければ偽、解釈できなければ 422。
fn flag(raw: Option<&str>, name: &str) -> Result<bool, ApiError> {
    match raw {
        None => Ok(false),
        Some(raw) => parse_bool(raw)
            .ok_or_else(|| ApiError::invalid(format!("{name} は真偽値で指定してください"))),
    }
}

/// FastAPI (pydantic) と同じ別名。大文字小文字は区別しない。
fn parse_bool(raw: &str) -> Option<bool> {
    match raw.to_ascii_lowercase().as_str() {
        "true" | "1" | "on" | "t" | "y" | "yes" => Some(true),
        "false" | "0" | "off" | "f" | "n" | "no" => Some(false),
        _ => None,
    }
}
