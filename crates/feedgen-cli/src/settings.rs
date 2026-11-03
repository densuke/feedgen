//! 引数と設定ファイルの統合 (api.md C-1、C-2)。

use feedgen_core::generator::GenerateOptions;

use crate::args::Args;
use crate::config::FileConfig;

#[derive(Debug)]
pub struct Settings {
    pub options: GenerateOptions,
    pub api_host: Option<String>,
}

/// 優先順位は、引数 > 設定ファイル > 既定。`user_agent` と `max_items` を検証する。
/// 既定の `user_agent` は `feedgen/1.0` (`GenerateOptions::default`)。
pub fn resolve(args: &Args, file: &FileConfig) -> Result<Settings, String> {
    let _ = (args, file);
    todo!("api.md C-1")
}
