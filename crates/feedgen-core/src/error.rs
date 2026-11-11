//! エラー型。必要になった時点で variant を足す。

use thiserror::Error;

/// フィード生成に関わるエラー。
#[derive(Debug, Error)]
pub enum FeedError {
    /// HTTP 取得に失敗した (通信、タイムアウト、上限超過など)。
    #[error("HTTP取得エラー: {0}")]
    Http(String),

    /// 取得を許可しない URL (内部アドレス、非 http(s)、解釈が割れる URL など)。
    /// メッセージには解決したアドレスなどの内部情報を含めない (docs/specs/ssrf.md S-9)。
    #[error("{0}")]
    UnsafeUrl(String),

    /// YouTube の検索の失敗 (キー未設定、API の失敗)。キーも API の応答の本文も含めない (youtube.md Y-7)。
    #[error("{0}")]
    YouTube(String),
}

/// クレート共通の Result 別名。
pub type Result<T> = std::result::Result<T, FeedError>;
