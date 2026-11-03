//! HTML の文字コードの判定と、文字列への変換 (docs/specs/pipeline.md G-9)。
//!
//! 文字コードは、BOM、`Content-Type` の `charset`、本文の先頭 1024 バイトの `<meta>` の順に決め、
//! どれもなければ UTF-8。`encoding_rs` が知らないラベル (「置換」の文字コードも含む) は、
//! ないものとして次へ進む。

use encoding_rs::{Encoding, REPLACEMENT, UTF_8, UTF_16BE, UTF_16LE};

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

/// `Content-Type` の `charset` パラメータの値 (二重・単一の引用符は除く)。なければ `None`。
pub(crate) fn charset_param(content_type: &str) -> Option<&str> {
    content_type
        .split(';')
        .skip(1)
        .find_map(|parameter| {
            let (name, value) = parameter.split_once('=')?;
            name.trim()
                .eq_ignore_ascii_case("charset")
                .then(|| value.trim().trim_matches(['"', '\'']))
        })
        .filter(|value| !value.is_empty())
}

/// `Content-Type` の `charset` が、知っているラベルのときだけ、その値を返す。
pub(crate) fn known_charset(content_type: &str) -> Option<&str> {
    charset_param(content_type).filter(|label| label_to_encoding(label).is_some())
}

/// ラベルを文字コードにする。未知のラベルと、「置換」の文字コード (`iso-2022-kr` など。使うと本文全体が
/// `U+FFFD` 1 文字になる) は `None`。
fn label_to_encoding(label: &str) -> Option<&'static Encoding> {
    Encoding::for_label(label.trim().as_bytes()).filter(|encoding| *encoding != REPLACEMENT)
}

/// 本文の先頭 1024 バイトの `<meta>` から、最初の、知っているラベルの文字コードを探す。
///
/// コメントの中は読まない。`<meta>` が UTF-16 を指すときは、UTF-8 とみなす (ASCII 互換の本文を
/// UTF-16 として読むと文字化けするため)。
fn charset_from_meta(body: &[u8]) -> Option<&'static Encoding> {
    let head = &body[..body.len().min(META_SCAN_LIMIT)];
    let mut at = 0;
    while let Some(offset) = head[at..].iter().position(|&b| b == b'<') {
        let rest = &head[at + offset..];
        if let Some(inside) = rest.strip_prefix(b"<!--") {
            let end = find(inside, b"-->")?;
            at = head.len() - inside.len() + end + b"-->".len();
            continue;
        }
        at += offset + 1;
        if !is_meta_start(rest) {
            continue;
        }
        let (attributes, after_tag) = read_attributes(&rest[b"<meta".len()..]);
        at = head.len() - after_tag.len();
        let encoding = charset_of_meta(&attributes).and_then(|label| label_to_encoding(&label));
        match encoding {
            Some(e) if e == UTF_16LE || e == UTF_16BE => return Some(UTF_8),
            Some(e) => return Some(e),
            None => {}
        }
    }
    None
}

/// `<meta` で始まり、その直後が空白、`/`、`>` のいずれか (`<metadata>` は `<meta>` ではない)。
fn is_meta_start(rest: &[u8]) -> bool {
    let tag = b"<meta";
    rest.len() > tag.len()
        && rest[..tag.len()].eq_ignore_ascii_case(tag)
        && (rest[tag.len()].is_ascii_whitespace() || matches!(rest[tag.len()], b'/' | b'>'))
}

/// `<meta` の後ろから、タグの終わりの `>` までの属性を読む。(属性のリスト, タグの後ろの残り)。
/// 属性名は小文字にする。同じ名前が複数あるときは、探す側が先頭のものを取る。
fn read_attributes(mut bytes: &[u8]) -> (Vec<(String, String)>, &[u8]) {
    let mut attributes = Vec::new();
    loop {
        bytes = skip_while(bytes, |b| b.is_ascii_whitespace() || b == b'/');
        match bytes.first() {
            None => return (attributes, bytes),
            Some(b'>') => return (attributes, &bytes[1..]),
            Some(_) => {}
        }
        // 名前。先頭が `=` のときも、1 文字は名前として進める (無限ループを避ける)。
        let name_end = 1 + bytes[1..]
            .iter()
            .position(|&b| b.is_ascii_whitespace() || matches!(b, b'=' | b'>' | b'/'))
            .unwrap_or(bytes.len() - 1);
        let name = String::from_utf8_lossy(&bytes[..name_end]).to_ascii_lowercase();
        bytes = skip_while(&bytes[name_end..], |b| b.is_ascii_whitespace());

        let mut value = String::new();
        if let Some(after_equals) = bytes.strip_prefix(b"=") {
            let after_equals = skip_while(after_equals, |b| b.is_ascii_whitespace());
            let (raw, rest) = match after_equals.first() {
                Some(&quote @ (b'"' | b'\'')) => {
                    let inner = &after_equals[1..];
                    let end = inner
                        .iter()
                        .position(|&b| b == quote)
                        .unwrap_or(inner.len());
                    (&inner[..end], &inner[(end + 1).min(inner.len())..])
                }
                _ => {
                    let end = after_equals
                        .iter()
                        .position(|&b| b.is_ascii_whitespace() || b == b'>')
                        .unwrap_or(after_equals.len());
                    (&after_equals[..end], &after_equals[end..])
                }
            };
            value = String::from_utf8_lossy(raw).into_owned();
            bytes = rest;
        }
        attributes.push((name, value));
    }
}

/// `<meta>` の属性から、`charset` のラベルを取り出す。
/// `charset` 属性、なければ、`http-equiv="Content-Type"` の `content` の中の `charset=…`。
fn charset_of_meta(attributes: &[(String, String)]) -> Option<String> {
    let attribute = |name: &str| {
        attributes
            .iter()
            .find(|(attribute_name, _)| attribute_name == name)
            .map(|(_, value)| value.as_str())
    };
    if let Some(label) = attribute("charset") {
        return Some(label.trim().to_string());
    }
    let is_content_type = attribute("http-equiv")?
        .trim()
        .eq_ignore_ascii_case("content-type");
    if !is_content_type {
        return None;
    }
    charset_in_content(attribute("content")?)
}

/// `text/html; charset=Shift_JIS` のような値から、`charset=` の後ろのラベルを取り出す。
fn charset_in_content(content: &str) -> Option<String> {
    let lower = content.to_ascii_lowercase();
    let after_name = &lower[lower.find("charset")? + "charset".len()..];
    let after_equals = after_name.trim_start().strip_prefix('=')?.trim_start();
    let value = after_equals.trim_start_matches(['"', '\'']);
    let end = value
        .find(|c: char| c.is_ascii_whitespace() || matches!(c, ';' | '"' | '\''))
        .unwrap_or(value.len());
    Some(value[..end].to_string()).filter(|label| !label.is_empty())
}

fn skip_while(bytes: &[u8], predicate: impl Fn(u8) -> bool) -> &[u8] {
    let start = bytes
        .iter()
        .position(|&b| !predicate(b))
        .unwrap_or(bytes.len());
    &bytes[start..]
}

fn find(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack.windows(needle.len()).position(|w| w == needle)
}

#[cfg(test)]
mod tests;
