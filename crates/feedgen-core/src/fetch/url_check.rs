//! URL 文字列の検査 (docs/specs/ssrf.md S-2、S-3)。

use url::Url;

use super::denied;
use crate::error::{FeedError, Result};

/// 検査側と接続側で host の解釈が割れる文字か。制御文字、空白、バックスラッシュ。
pub(super) fn check_chars(raw: &str) -> Result<()> {
    if raw
        .chars()
        .any(|c| c.is_ascii_control() || c == ' ' || c == '\\')
    {
        return Err(denied());
    }
    Ok(())
}

/// URL 文字列を検査し、解析済みの `Url` を返す。
///
/// 解析前の生の文字列で文字・認証部・空の authority を弾き、1 回だけ解析する。
/// 以後の検査と接続には、この `Url` をそのまま使う。
pub fn check_url(raw: &str) -> Result<Url> {
    check_chars(raw)?;
    let (_, rest) = raw.split_once("://").ok_or_else(denied)?;
    let authority = rest.split(['/', '?', '#']).next().unwrap_or("");
    if authority.is_empty() {
        return Err(FeedError::UnsafeUrl("URL にホストがありません".into()));
    }
    if authority.contains('@') {
        return Err(denied());
    }

    let url = Url::parse(raw).map_err(|_| denied())?;
    if !matches!(url.scheme(), "http" | "https") {
        return Err(FeedError::UnsafeUrl(
            "http または https の URL のみ取得できます".into(),
        ));
    }
    if url.host().is_none() {
        return Err(FeedError::UnsafeUrl("URL にホストがありません".into()));
    }
    Ok(url)
}
