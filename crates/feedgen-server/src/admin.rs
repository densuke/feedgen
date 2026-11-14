//! 管理ページ (docs/specs/admin.md)。足場 (RED)。実装は GREEN の段階で行う。

/// 埋め込む HTML。実装では `include_str!("admin.html")` にする。
pub const PAGE: &str = "";

/// 管理ページを有効にするか (M-1)。引数があれば有効。なければ、環境変数 `FEEDGEN_ADMIN` が
/// `1` か `true` (大文字小文字を区別しない) のときだけ有効。
pub fn resolve_admin(arg: bool, env: Option<&str>) -> bool {
    let _ = (arg, env);
    todo!("admin.md M-1")
}
