//! 待ち受けアドレスの決定 (api.md A-8)。

use std::net::SocketAddr;

/// 引数 > 環境変数 > 既定 (`127.0.0.1:8000`) の順で決める。不正な値は理由の文字列。
pub fn resolve_bind(
    host_arg: Option<&str>,
    port_arg: Option<u16>,
    host_env: Option<&str>,
    port_env: Option<&str>,
) -> Result<SocketAddr, String> {
    let _ = (host_arg, port_arg, host_env, port_env);
    todo!("api.md A-8")
}
