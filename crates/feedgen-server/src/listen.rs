//! 待ち受けアドレスの決定 (api.md A-8)。

use std::net::{IpAddr, SocketAddr};

const DEFAULT_HOST: &str = "127.0.0.1";
const DEFAULT_PORT: u16 = 8000;

/// 引数 > 環境変数 > 既定 (`127.0.0.1:8000`) の順で決める。不正な値は理由の文字列。
pub fn resolve_bind(
    host_arg: Option<&str>,
    port_arg: Option<u16>,
    host_env: Option<&str>,
    port_env: Option<&str>,
) -> Result<SocketAddr, String> {
    // 空文字の環境変数は、未設定として扱う (systemd の `Environment=FEEDGEN_HOST=` など)。
    let host_env = host_env.filter(|value| !value.is_empty());
    let port_env = port_env.filter(|value| !value.is_empty());
    let host = host_arg.or(host_env).unwrap_or(DEFAULT_HOST);
    let ip: IpAddr = host
        .parse()
        .map_err(|_| format!("ホストを解釈できません: {host}"))?;
    let port = match (port_arg, port_env) {
        (Some(port), _) => port,
        (None, Some(raw)) => raw
            .parse()
            .map_err(|_| format!("ポートを解釈できません: {raw}"))?,
        (None, None) => DEFAULT_PORT,
    };
    Ok(SocketAddr::new(ip, port))
}
