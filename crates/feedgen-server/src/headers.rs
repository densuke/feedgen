//! `X-Existing-Feed-*` ヘッダの値の作成 (api.md A-7)。

/// タイトルをヘッダの値にする。制御文字を除き、200 文字に切り、可視 ASCII 以外を UTF-8 のバイトごとに `%XX` にする。
pub fn encode_title(title: &str) -> String {
    let _ = title;
    todo!("api.md A-7")
}
