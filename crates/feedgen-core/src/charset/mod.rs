//! HTML の文字コードの判定と、文字列への変換 (docs/specs/pipeline.md G-9)。
//!
//! 文字コードは、BOM、`Content-Type` の `charset`、本文の先頭 1024 バイトの `<meta>` の順に決め、
//! どれもなければ UTF-8。`encoding_rs` が知らないラベルは、ないものとして次へ進む。

use encoding_rs::{Encoding, UTF_8};

/// `<meta>` を探す、本文の先頭のバイト数。
const META_SCAN_LIMIT: usize = 1024;

/// HTML の本文 (バイト列) を、UTF-8 の文字列にする。不正なバイト列は `U+FFFD` にする (失敗しない)。
pub fn decode_html(body: &[u8], content_type: &str) -> String {
    if let Some((encoding, _)) = Encoding::for_bom(body) {
        return encoding.decode_with_bom_removal(body).0.into_owned();
    }
    let encoding = charset_param(content_type)
        .and_then(label_to_encoding)
        .or_else(|| charset_from_meta(body))
        .unwrap_or(UTF_8);
    encoding.decode_without_bom_handling(body).0.into_owned()
}

/// `Content-Type` の `charset` パラメータの値 (引用符は除く)。なければ `None`。
pub(crate) fn charset_param(content_type: &str) -> Option<&str> {
    content_type
        .split(';')
        .skip(1)
        .find_map(|parameter| {
            let (name, value) = parameter.split_once('=')?;
            name.trim()
                .eq_ignore_ascii_case("charset")
                .then(|| value.trim().trim_matches('"'))
        })
        .filter(|value| !value.is_empty())
}

fn label_to_encoding(label: &str) -> Option<&'static Encoding> {
    Encoding::for_label(label.trim().as_bytes())
}

/// 本文の先頭 1024 バイトにある `<meta>` から、最初の、知っているラベルの `charset` を探す。
fn charset_from_meta(body: &[u8]) -> Option<&'static Encoding> {
    let head = body[..body.len().min(META_SCAN_LIMIT)].to_ascii_lowercase();
    let mut rest = head.as_slice();
    while let Some(start) = find(rest, b"<meta") {
        let tag_and_after = &rest[start + b"<meta".len()..];
        let tag_end = tag_and_after
            .iter()
            .position(|&b| b == b'>')
            .unwrap_or(tag_and_after.len());
        let tag = &tag_and_after[..tag_end];
        if let Some(encoding) = charset_in_tag(tag).and_then(label_to_encoding) {
            return Some(encoding);
        }
        rest = &tag_and_after[tag_end..];
    }
    None
}

/// `<meta …>` の中身から、`charset=` の値 (二重・単一の引用符、なしのいずれも可) を取り出す。
fn charset_in_tag(tag: &[u8]) -> Option<&str> {
    let mut rest = tag;
    while let Some(at) = find(rest, b"charset") {
        rest = &rest[at + b"charset".len()..];
        let after_name = trim_ascii_start(rest);
        let Some(after_equals) = after_name.strip_prefix(b"=") else {
            continue;
        };
        let value = trim_ascii_start(after_equals);
        let value = match value.first() {
            Some(&quote @ (b'"' | b'\'')) => {
                let inner = &value[1..];
                &inner[..inner
                    .iter()
                    .position(|&b| b == quote)
                    .unwrap_or(inner.len())]
            }
            _ => {
                let end = value
                    .iter()
                    .position(|&b| {
                        // `content="text/html; charset=x"` のように、値の後ろに属性の引用符が来る形も終端にする。
                        b.is_ascii_whitespace() || matches!(b, b';' | b'>' | b'/' | b'"' | b'\'')
                    })
                    .unwrap_or(value.len());
                &value[..end]
            }
        };
        return std::str::from_utf8(value).ok().filter(|v| !v.is_empty());
    }
    None
}

fn find(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack.windows(needle.len()).position(|w| w == needle)
}

fn trim_ascii_start(bytes: &[u8]) -> &[u8] {
    let start = bytes
        .iter()
        .position(|b| !b.is_ascii_whitespace())
        .unwrap_or(bytes.len());
    &bytes[start..]
}

#[cfg(test)]
mod tests;
