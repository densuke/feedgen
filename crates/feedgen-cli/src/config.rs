//! 設定ファイル (api.md C-2)。

use std::path::Path;

use serde::Deserialize;

/// 読む項目は 3 つだけ。
#[derive(Debug, Default, Deserialize, PartialEq, Eq)]
pub struct FileConfig {
    pub max_items: Option<u16>,
    pub user_agent: Option<String>,
    pub api_base_url: Option<String>,
}

/// 読み込んだ設定と、無視した未知のキーの警告。
#[derive(Debug, Default)]
pub struct Loaded {
    pub config: FileConfig,
    pub warnings: Vec<String>,
}

/// YAML の文字列を読む。YAML として不正、または型が違うときは理由の文字列。
pub fn parse_config(yaml: &str) -> Result<Loaded, String> {
    let _ = yaml;
    todo!("api.md C-2")
}

/// `explicit` があればそのファイル (なければエラー)、なければ `cwd/config.yaml` (なければ設定なし)。
pub fn load_config(explicit: Option<&Path>, cwd: &Path) -> Result<Loaded, String> {
    let _ = (explicit, cwd);
    todo!("api.md C-2")
}
