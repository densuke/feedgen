//! 設定ファイル (api.md C-2)。

use std::io::ErrorKind;
use std::path::Path;

use serde::Deserialize;
use serde_yaml_ng::Value;

const KNOWN_KEYS: [&str; 3] = ["max_items", "user_agent", "api_base_url"];
const DEFAULT_FILE: &str = "config.yaml";

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
    let value: Value =
        serde_yaml_ng::from_str(yaml).map_err(|e| format!("設定ファイルを解釈できません: {e}"))?;
    let warnings = match &value {
        Value::Mapping(map) => map
            .keys()
            .map(|key| key.as_str().unwrap_or("(文字列でないキー)"))
            .filter(|key| !KNOWN_KEYS.contains(key))
            .map(|key| format!("設定ファイルの未知のキーを無視しました: {key}"))
            .collect(),
        _ => Vec::new(),
    };
    let config = match value {
        Value::Null => FileConfig::default(),
        other => serde_yaml_ng::from_value(other)
            .map_err(|e| format!("設定ファイルの値が不正です: {e}"))?,
    };
    Ok(Loaded { config, warnings })
}

/// `explicit` があればそのファイル (なければエラー)、なければ `cwd/config.yaml` (なければ設定なし)。
pub fn load_config(explicit: Option<&Path>, cwd: &Path) -> Result<Loaded, String> {
    let (path, required) = match explicit {
        Some(path) => (path.to_path_buf(), true),
        None => (cwd.join(DEFAULT_FILE), false),
    };
    match std::fs::read_to_string(&path) {
        Ok(text) => parse_config(&text),
        Err(e) if !required && e.kind() == ErrorKind::NotFound => Ok(Loaded::default()),
        Err(e) => Err(format!("設定ファイルを読めません: {}: {e}", path.display())),
    }
}
