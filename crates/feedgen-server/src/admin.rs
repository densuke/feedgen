//! 管理ページ (docs/specs/admin.md)。静的な HTML 1 枚を、バイナリに埋め込んで配信する。

use axum::http::header::{
    CACHE_CONTROL, CONTENT_SECURITY_POLICY, CONTENT_TYPE, REFERRER_POLICY, X_CONTENT_TYPE_OPTIONS,
    X_FRAME_OPTIONS,
};
use axum::response::{IntoResponse, Response};

/// 埋め込む HTML。
pub const PAGE: &str = include_str!("admin.html");

/// 外部のリソースを読まない前提 (M-3)。スクリプトとスタイルは、HTML の中にある。
const CSP: &str = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; \
connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";

/// 管理ページを有効にするか (M-1)。引数があれば有効。なければ、環境変数 `FEEDGEN_ADMIN` が
/// `1` か `true` (大文字小文字を区別しない) のときだけ有効。
pub fn resolve_admin(arg: bool, env: Option<&str>) -> bool {
    arg || env.is_some_and(|value| value == "1" || value.eq_ignore_ascii_case("true"))
}

pub(crate) async fn page() -> Response {
    (
        [
            (CONTENT_TYPE, "text/html; charset=utf-8"),
            (CACHE_CONTROL, "no-store"),
            (X_CONTENT_TYPE_OPTIONS, "nosniff"),
            (X_FRAME_OPTIONS, "DENY"),
            (REFERRER_POLICY, "no-referrer"),
            (CONTENT_SECURITY_POLICY, CSP),
        ],
        PAGE,
    )
        .into_response()
}
