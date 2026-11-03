//! HTML の文字コードの判定と、文字列への変換 (docs/specs/pipeline.md G-9)。
//!
//! RED 段階のスタブ。実装は仕様に従って後続のコミットで書く。

/// HTML の本文 (バイト列) を、UTF-8 の文字列にする。
///
/// 文字コードは、BOM、`Content-Type` の `charset`、本文の先頭 1024 バイトの `<meta>` の順に決め、
/// どれもなければ UTF-8。不正なバイト列は `U+FFFD` にする (失敗しない)。
pub fn decode_html(_body: &[u8], _content_type: &str) -> String {
    todo!("G-9")
}

#[cfg(test)]
mod tests;
