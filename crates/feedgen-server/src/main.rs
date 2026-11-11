//! サーバーの起動。引数の決定は `listen::resolve_bind` (テスト済み)。ここは配線だけで、テストしない。

use std::process::ExitCode;
use std::sync::Arc;
use std::time::Duration;

use feedgen_core::generator::FeedGenerator;
use feedgen_server::listen::resolve_bind;
use feedgen_server::{AppConfig, router};
use tokio::sync::watch;

const SHUTDOWN_GRACE: Duration = Duration::from_secs(30);

fn parse_args() -> Result<(Option<String>, Option<u16>), String> {
    let (mut host, mut port) = (None, None);
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        let mut next = |name: &str| args.next().ok_or(format!("{name} に値がありません"));
        match arg.as_str() {
            "--host" => host = Some(next("--host")?),
            "--port" => {
                let raw = next("--port")?;
                port = Some(
                    raw.parse()
                        .map_err(|_| format!("ポートを解釈できません: {raw}"))?,
                );
            }
            other => return Err(format!("不明な引数です: {other}")),
        }
    }
    Ok((host, port))
}

/// SIGTERM か Ctrl-C を待つ。登録に失敗したら、ログに出し、その信号では終了しない。
async fn wait_for_signal() {
    let mut terminate =
        match tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()) {
            Ok(signal) => Some(signal),
            Err(error) => {
                eprintln!("警告: SIGTERM を受け取れません: {error}");
                None
            }
        };
    tokio::select! {
        result = tokio::signal::ctrl_c() => match result {
            Ok(()) => {}
            Err(error) => {
                eprintln!("警告: Ctrl-C を受け取れません: {error}");
                std::future::pending::<()>().await;
            }
        },
        _ = async {
            match terminate.as_mut() {
                Some(signal) => { signal.recv().await; }
                None => std::future::pending::<()>().await,
            }
        } => {}
    }
}

#[tokio::main]
async fn main() -> ExitCode {
    let (host, port) = match parse_args() {
        Ok(parsed) => parsed,
        Err(message) => {
            eprintln!("エラー: {message}");
            return ExitCode::from(2);
        }
    };
    let address = match resolve_bind(
        host.as_deref(),
        port,
        std::env::var("FEEDGEN_HOST").ok().as_deref(),
        std::env::var("FEEDGEN_PORT").ok().as_deref(),
    ) {
        Ok(address) => address,
        Err(message) => {
            eprintln!("エラー: {message}");
            return ExitCode::from(2);
        }
    };
    let listener = match tokio::net::TcpListener::bind(address).await {
        Ok(listener) => listener,
        Err(error) => {
            eprintln!("エラー: {address} で待ち受けできません: {error}");
            return ExitCode::FAILURE;
        }
    };
    eprintln!("待ち受け開始: {address}");

    let app = router(
        Arc::new(FeedGenerator::new().with_youtube_api_key(std::env::var("YOUTUBE_API_KEY").ok())),
        AppConfig::default(),
    );
    let (stop, mut graceful) = watch::channel(false);
    let mut deadline = stop.subscribe();
    tokio::spawn(async move {
        wait_for_signal().await;
        let _ = stop.send(true);
    });
    let server = axum::serve(listener, app).with_graceful_shutdown(async move {
        let _ = graceful.changed().await;
    });
    let forced = async move {
        let _ = deadline.changed().await;
        tokio::time::sleep(SHUTDOWN_GRACE).await;
    };
    tokio::select! {
        result = server => match result {
            Ok(()) => ExitCode::SUCCESS,
            Err(error) => {
                eprintln!("エラー: {error}");
                ExitCode::FAILURE
            }
        },
        _ = forced => {
            eprintln!("終了待ちが上限を超えたため、強制終了します");
            ExitCode::FAILURE
        }
    }
}
