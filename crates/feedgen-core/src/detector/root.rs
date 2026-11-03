//! 本文がフィードそのものかの判定 (docs/specs/detector.md D-5、D-6)。
//!
//! XML パーサは使わず、先頭から前置き (BOM、空白、XML 宣言、コメント、DOCTYPE) を読み飛ばして、
//! ルート要素の名前だけを見る。

use super::RootKind;

/// 走査する先頭のバイト数。
const SCAN_LIMIT: usize = 64 * 1024;

const UTF8_BOM: &[u8] = b"\xEF\xBB\xBF";

/// 本文のルート要素がフィードのものなら、その種類を返す。
pub(super) fn feed_root(body: &[u8]) -> Option<RootKind> {
    let limited = &body[..body.len().min(SCAN_LIMIT)];
    let mut rest = limited.strip_prefix(UTF8_BOM).unwrap_or(limited);
    loop {
        rest = trim_ascii_start(rest);
        if let Some(after) = rest.strip_prefix(b"<?") {
            rest = skip_past(after, b"?>")?;
        } else if let Some(after) = rest.strip_prefix(b"<!--") {
            rest = skip_past(after, b"-->")?;
        } else if rest.starts_with(b"<!") {
            rest = skip_declaration(rest)?;
        } else {
            break;
        }
    }

    let tag = rest.strip_prefix(b"<")?;
    let name_end = tag
        .iter()
        .position(|b| b.is_ascii_whitespace() || matches!(b, b'>' | b'/'))
        .unwrap_or(tag.len());
    // 名前空間の接頭辞 (`atom:feed` の `atom:`) を除く。
    let local_name = tag[..name_end].rsplit(|b| *b == b':').next()?;
    match local_name {
        b"rss" => Some(RootKind::Rss),
        b"RDF" => Some(RootKind::Rdf),
        b"feed" => Some(RootKind::Atom),
        _ => None,
    }
}

/// 代理取得で返す `Content-Type`。`original` に `charset` があれば引き継ぐ。
pub(super) fn proxied_content_type(root: RootKind, original: &str) -> String {
    let media_type = match root {
        RootKind::Rss | RootKind::Rdf => "application/rss+xml",
        RootKind::Atom => "application/atom+xml",
    };
    match charset_of(original) {
        Some(charset) => format!("{media_type}; charset={charset}"),
        None => media_type.to_string(),
    }
}

fn charset_of(content_type: &str) -> Option<&str> {
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

fn trim_ascii_start(bytes: &[u8]) -> &[u8] {
    let start = bytes
        .iter()
        .position(|b| !b.is_ascii_whitespace())
        .unwrap_or(bytes.len());
    &bytes[start..]
}

fn find(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack.windows(needle.len()).position(|w| w == needle)
}

/// `needle` の直後から始まる残りを返す。なければ `None`。
fn skip_past<'a>(haystack: &'a [u8], needle: &[u8]) -> Option<&'a [u8]> {
    find(haystack, needle).map(|at| &haystack[at + needle.len()..])
}

/// `<!DOCTYPE …>` などの宣言を読み飛ばす。内部サブセット `[…]` の中の、コメントと引用符つきの文字列は、
/// 区切りとして数えない。
fn skip_declaration(rest: &[u8]) -> Option<&[u8]> {
    let mut i = 2;
    let mut depth = 0usize;
    let mut quote: Option<u8> = None;
    while i < rest.len() {
        let byte = rest[i];
        if let Some(open) = quote {
            if byte == open {
                quote = None;
            }
        } else if rest[i..].starts_with(b"<!--") {
            i += 4 + find(&rest[i + 4..], b"-->")? + 3;
            continue;
        } else {
            match byte {
                b'"' | b'\'' => quote = Some(byte),
                b'[' => depth += 1,
                b']' => depth = depth.saturating_sub(1),
                b'>' if depth == 0 => return Some(&rest[i + 1..]),
                _ => {}
            }
        }
        i += 1;
    }
    None
}
