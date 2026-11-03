//! CLI の本体 (api.md C-1、C-3)。入出力は戻り値にして、テストできるようにする。

use std::future::Future;
use std::path::Path;

use chrono::{DateTime, FixedOffset};
use feedgen_core::Result;
use feedgen_core::generator::{FeedGenerator, GenerateOptions, Outcome};

use crate::args::Args;
use crate::config::load_config;
use crate::settings::resolve;
use crate::url_gen::{UrlParams, generate_api_url};

pub trait FeedSource {
    fn generate(
        &self,
        url: &str,
        options: &GenerateOptions,
        now: DateTime<FixedOffset>,
    ) -> impl Future<Output = Result<Outcome>>;
}

impl FeedSource for FeedGenerator {
    async fn generate(
        &self,
        url: &str,
        options: &GenerateOptions,
        now: DateTime<FixedOffset>,
    ) -> Result<Outcome> {
        FeedGenerator::generate(self, url, options, now).await
    }
}

/// 実行の結果。`stdout` はバイト列 (代理取得は変換しない)。
#[derive(Debug)]
pub struct Report {
    pub exit_code: i32,
    pub stdout: Vec<u8>,
    pub stderr: String,
}

fn failure(mut stderr: String, message: &str) -> Report {
    stderr.push_str(&format!("エラー: {message}\n"));
    Report {
        exit_code: 1,
        stdout: Vec::new(),
        stderr,
    }
}

/// `-o` があればファイルに書き、なければ標準出力に回す。
fn deliver(args: &Args, mut stderr: String, bytes: Vec<u8>) -> Report {
    match &args.output {
        None => Report {
            exit_code: 0,
            stdout: bytes,
            stderr,
        },
        Some(path) => match std::fs::write(path, bytes) {
            Ok(()) => {
                stderr.push_str(&format!("出力しました: {}\n", path.display()));
                Report {
                    exit_code: 0,
                    stdout: Vec::new(),
                    stderr,
                }
            }
            Err(e) => failure(stderr, &format!("{} に書けません: {e}", path.display())),
        },
    }
}

/// 取得先の文字列から制御文字 (ANSI のエスケープ、改行など) を除く。端末の表示を書き換えさせない。
fn printable(text: &str) -> String {
    text.chars().filter(|c| !c.is_control()).collect()
}

/// 設定を読み、`--generate-url` ならURLを、そうでなければフィードを出力する。
/// `-o` があれば `stdout` は空で、ファイルに書く。失敗は終了コード 1 と `stderr` のメッセージ。
pub async fn run(
    args: &Args,
    cwd: &Path,
    source: &impl FeedSource,
    now: DateTime<FixedOffset>,
) -> Report {
    let loaded = match load_config(args.config.as_deref(), cwd) {
        Ok(loaded) => loaded,
        Err(message) => return failure(String::new(), &message),
    };
    let stderr: String = loaded
        .warnings
        .iter()
        .map(|warning| format!("警告: {warning}\n"))
        .collect();
    let settings = match resolve(args, &loaded.config) {
        Ok(settings) => settings,
        Err(message) => return failure(stderr, &message),
    };

    if args.generate_url {
        let Some(host) = &settings.api_host else {
            return failure(
                stderr,
                "--api-host か、設定ファイルの api_base_url が必要です",
            );
        };
        let params = UrlParams {
            max_items: args.max_items.or(loaded.config.max_items),
            use_feed: args.use_feed,
            feed_first: args.feed_first,
            user_agent: args
                .user_agent
                .clone()
                .or_else(|| loaded.config.user_agent.clone()),
        };
        return match generate_api_url(host, &args.url, &params) {
            Ok(url) => deliver(args, stderr, format!("{url}\n").into_bytes()),
            Err(message) => failure(stderr, &message),
        };
    }

    match source.generate(&args.url, &settings.options, now).await {
        Err(e) => failure(stderr, &e.to_string()),
        Ok(Outcome::Proxied { body, .. }) => deliver(args, stderr, body),
        Ok(Outcome::Generated { feed, detected }) => {
            let mut stderr = stderr;
            if let Some(first) = detected.first() {
                stderr.push_str(&format!(
                    "既存フィード: {} {} ({})\n",
                    first.kind.label(),
                    first.url,
                    printable(&first.title)
                ));
            }
            deliver(args, stderr, feed.to_xml(now).into_bytes())
        }
    }
}
