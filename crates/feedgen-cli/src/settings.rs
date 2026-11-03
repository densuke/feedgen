//! 引数と設定ファイルの統合 (api.md C-1、C-2)。

use feedgen_core::generator::{GenerateOptions, validate_user_agent};

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
    let defaults = GenerateOptions::default();
    let max_items = match args.max_items.or(file.max_items) {
        None => defaults.max_items,
        Some(n) if (1..=100).contains(&n) => usize::from(n),
        Some(_) => return Err("max_items は 1〜100 で指定してください".to_string()),
    };
    let user_agent = args
        .user_agent
        .clone()
        .or_else(|| file.user_agent.clone())
        .unwrap_or(defaults.user_agent);
    validate_user_agent(&user_agent)?;
    Ok(Settings {
        options: GenerateOptions {
            max_items,
            user_agent,
            use_feed: args.use_feed,
            feed_first: args.feed_first,
        },
        api_host: args.api_host.clone().or_else(|| file.api_base_url.clone()),
    })
}
