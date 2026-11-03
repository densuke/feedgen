//! `--generate-url` (api.md C-4)。Python 版 `URLGenerator` と同じ形。

/// 指定されたものだけをクエリに入れる。真偽値は、真のときだけ入れる。
#[derive(Debug, Default, Clone)]
pub struct UrlParams {
    pub max_items: Option<u16>,
    pub use_feed: bool,
    pub feed_first: bool,
    pub user_agent: Option<String>,
}

/// `{正規化した api_host}/feed?url=…` を作る。ホストが不正なら理由の文字列。
pub fn generate_api_url(
    api_host: &str,
    target: &str,
    params: &UrlParams,
) -> Result<String, String> {
    let _ = (api_host, target, params);
    todo!("api.md C-4")
}
