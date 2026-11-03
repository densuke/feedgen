//! `X-Existing-Feed-*` ヘッダの値の作成 (api.md A-7)。

const MAX_TITLE_CHARS: usize = 200;

/// タイトルをヘッダの値にする。制御文字を除き、200 文字に切り、可視 ASCII 以外を UTF-8 のバイトごとに `%XX` にする。
pub fn encode_title(title: &str) -> String {
    let mut encoded = String::new();
    for c in title
        .chars()
        .filter(|c| !c.is_control())
        .take(MAX_TITLE_CHARS)
    {
        if c.is_ascii() {
            encoded.push(c);
        } else {
            let mut buffer = [0u8; 4];
            for byte in c.encode_utf8(&mut buffer).bytes() {
                encoded.push_str(&format!("%{byte:02X}"));
            }
        }
    }
    encoded
}
