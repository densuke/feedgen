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
    let base = normalize_host(api_host)?;
    let mut query = vec![("url", target.to_string())];
    if let Some(n) = params.max_items {
        query.push(("max_items", n.to_string()));
    }
    if params.use_feed {
        query.push(("use_feed", "true".to_string()));
    }
    if params.feed_first {
        query.push(("feed_first", "true".to_string()));
    }
    if let Some(user_agent) = &params.user_agent {
        query.push(("user_agent", user_agent.clone()));
    }
    let query: Vec<String> = query
        .iter()
        .map(|(name, value)| format!("{name}={}", quote_plus(value)))
        .collect();
    Ok(format!("{base}/feed?{}", query.join("&")))
}

/// スキームがなければ `https://` を付け、末尾の `/` を除く。ホストが空ならエラー。
fn normalize_host(api_host: &str) -> Result<String, String> {
    let trimmed = api_host.trim();
    let with_scheme = if trimmed.contains("://") {
        trimmed.to_string()
    } else {
        format!("https://{trimmed}")
    };
    let authority = with_scheme
        .split_once("://")
        .and_then(|(_, rest)| rest.split('/').next())
        .unwrap_or("");
    if authority.is_empty() {
        return Err(format!("API のホストを解釈できません: {api_host:?}"));
    }
    Ok(with_scheme.trim_end_matches('/').to_string())
}

/// Python の `urllib.parse.quote_plus` と同じ。英数字と `_.-~` 以外は UTF-8 のバイトごとに `%XX`、空白は `+`。
fn quote_plus(value: &str) -> String {
    let mut out = String::new();
    for byte in value.bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'_' | b'.' | b'-' | b'~' => {
                out.push(char::from(byte))
            }
            b' ' => out.push('+'),
            _ => out.push_str(&format!("%{byte:02X}")),
        }
    }
    out
}
