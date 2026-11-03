//! CLI の本体 (api.md C-1、C-3)。入出力は戻り値にして、テストできるようにする。

use std::future::Future;
use std::path::Path;

use chrono::{DateTime, FixedOffset};
use feedgen_core::Result;
use feedgen_core::generator::{FeedGenerator, GenerateOptions, Outcome};

use crate::args::Args;

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

/// 設定を読み、`--generate-url` ならURLを、そうでなければフィードを出力する。
/// `-o` があれば `stdout` は空で、ファイルに書く。失敗は終了コード 1 と `stderr` のメッセージ。
pub async fn run(
    args: &Args,
    cwd: &Path,
    source: &impl FeedSource,
    now: DateTime<FixedOffset>,
) -> Report {
    let _ = (args, cwd, source, now);
    todo!("api.md C-1")
}
