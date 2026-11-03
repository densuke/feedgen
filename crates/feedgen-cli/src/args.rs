//! コマンドライン引数 (api.md C-1)。

use std::path::PathBuf;

use clap::Parser;

#[derive(Debug, Parser)]
#[command(name = "feedgen", about = "URL から RSS を生成する")]
pub struct Args {
    /// 対象の URL
    pub url: String,
    /// 設定ファイル
    #[arg(short = 'c', long)]
    pub config: Option<PathBuf>,
    /// 出力先のファイル (なければ標準出力)
    #[arg(short = 'o', long)]
    pub output: Option<PathBuf>,
    /// 最大記事数 (1〜100)
    #[arg(long, value_parser = clap::value_parser!(u16).range(1..=100))]
    pub max_items: Option<u16>,
    #[arg(long)]
    pub user_agent: Option<String>,
    /// 既存フィードがあれば代理取得
    #[arg(long)]
    pub use_feed: bool,
    /// 既存フィードの検出結果を stderr に出し、HTML 解析も続ける
    #[arg(long)]
    pub feed_first: bool,
    /// Web API の URL を生成して出力する (取得しない)
    #[arg(long)]
    pub generate_url: bool,
    /// `--generate-url` の API のホスト
    #[arg(long)]
    pub api_host: Option<String>,
}
