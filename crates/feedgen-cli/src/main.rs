use std::process::ExitCode;

use chrono::Utc;
use clap::Parser;
use feedgen_cli::Args;
use feedgen_cli::run::run;
use feedgen_core::generator::FeedGenerator;

#[tokio::main]
async fn main() -> ExitCode {
    let args = Args::parse();
    let cwd = match std::env::current_dir() {
        Ok(cwd) => cwd,
        Err(error) => {
            eprintln!("エラー: カレントディレクトリを取得できません: {error}");
            return ExitCode::FAILURE;
        }
    };
    let now = Utc::now().fixed_offset();
    let report = run(&args, &cwd, &FeedGenerator::new(), now).await;
    eprint!("{}", report.stderr);
    {
        use std::io::Write;
        if let Err(error) = std::io::stdout().write_all(&report.stdout) {
            eprintln!("エラー: 標準出力に書けません: {error}");
            return ExitCode::FAILURE;
        }
    }
    if report.exit_code == 0 {
        ExitCode::SUCCESS
    } else {
        ExitCode::FAILURE
    }
}
