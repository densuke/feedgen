//! 文字列の取り出しと、木の探索の小さな道具 (docs/specs/parser.md P-2、2.3、2.4)。

use scraper::{ElementRef, Html, Node, Selector};

/// `get_text()` から外す要素 (Python 版 BeautifulSoup の挙動)。
const EXCLUDED: [&str; 5] = ["script", "style", "template", "rt", "rp"];

/// 空白をまとめない要素 (BeautifulSoup の `preserve_whitespace_tags`)。
const PRESERVE_WHITESPACE: [&str; 2] = ["pre", "textarea"];

/// 子孫のテキストを区切りなしで連結する。`EXCLUDED` の中身とコメントは含めない (P-2)。
/// 空白だけのテキストは、`pre` / `textarea` の中を除き、短くまとめる (2.3)。
///
/// `element` 自身が `EXCLUDED` の内側にある (祖先に `EXCLUDED` の要素がある) ときは空文字列。
/// BeautifulSoup は、これらの内側にある文字列を入れ子の深さにかかわらず除外するため。
pub(super) fn text_of(element: ElementRef) -> String {
    let inside_excluded = element
        .ancestors()
        .filter_map(ElementRef::wrap)
        .any(|ancestor| EXCLUDED.contains(&ancestor.value().name()));
    if inside_excluded {
        return String::new();
    }
    // `<pre>` / `<textarea>` の内側かどうか (自身を含む)。内側では空白をまとめない。
    let preserve = element
        .ancestors()
        .filter_map(ElementRef::wrap)
        .chain(std::iter::once(element))
        .any(|e| PRESERVE_WHITESPACE.contains(&e.value().name()));
    let mut out = String::new();
    push_text(element, preserve, &mut out);
    out
}

fn push_text(element: ElementRef, preserve: bool, out: &mut String) {
    for child in element.children() {
        if let Some(child_element) = ElementRef::wrap(child) {
            if !EXCLUDED.contains(&child_element.value().name()) {
                let preserve =
                    preserve || PRESERVE_WHITESPACE.contains(&child_element.value().name());
                push_text(child_element, preserve, out);
            }
        } else if let Node::Text(text) = child.value() {
            match collapsed_whitespace(text) {
                Some(collapsed) if !preserve => out.push_str(collapsed),
                _ => out.push_str(text),
            }
        }
    }
}

/// 空白だけのテキストを、`\n` を含めば `\n`、含まなければ `' '` にまとめる (2.3)。
/// 空白は ASCII の 5 種 (U+0020、U+0009、U+000A、U+000C、U+000D) だけ。NBSP や U+000B は含めない。
/// 空白だけでなければ `None`。
fn collapsed_whitespace(text: &str) -> Option<&'static str> {
    let whitespace_only = text
        .chars()
        .all(|c| matches!(c, ' ' | '\t' | '\n' | '\u{c}' | '\r'));
    whitespace_only.then(|| if text.contains('\n') { "\n" } else { " " })
}

/// 固定の CSS セレクタを作る。呼び出し側の文字列はすべてこのクレート内の定数で、テストで有効性を確かめる。
pub(super) fn selector(css: &str) -> Selector {
    Selector::parse(css).expect("固定のセレクタは常に有効")
}

/// 先頭 `limit` 文字に切る。切ったときだけ `...` を付ける。文字はコードポイント単位。
pub(super) fn cut(text: &str, limit: usize) -> String {
    match text.char_indices().nth(limit) {
        Some((end, _)) => format!("{}...", &text[..end]),
        None => text.to_string(),
    }
}

/// 先頭 `limit` 文字に切る (`...` なし)。
pub(super) fn first_chars(text: &str, limit: usize) -> String {
    text.chars().take(limit).collect()
}

/// 自分自身を除く、子孫の要素 (文書順)。
pub(super) fn descendant_elements(element: ElementRef) -> impl Iterator<Item = ElementRef> {
    element.descendants().skip(1).filter_map(ElementRef::wrap)
}

/// 子孫のうち、名前が `names` のどれかである最初の要素。
pub(super) fn first_descendant<'a>(
    element: ElementRef<'a>,
    names: &[&str],
) -> Option<ElementRef<'a>> {
    descendant_elements(element).find(|e| names.contains(&e.value().name()))
}

/// 文書順で `element` の次にある、名前が `names` のどれかである要素。
/// `element` 自身の子孫も対象 (Python 版の `find_next` と同じ)。
pub(super) fn find_next<'a>(
    document: &'a Html,
    element: ElementRef<'a>,
    names: &[&str],
) -> Option<ElementRef<'a>> {
    document
        .tree
        .root()
        .descendants()
        .skip_while(|node| node.id() != element.id())
        .skip(1)
        .filter_map(ElementRef::wrap)
        .find(|e| names.contains(&e.value().name()))
}

/// 見出しの説明 (2.4)。
pub(super) fn heading_description(document: &Html, heading: ElementRef) -> String {
    if let Some(next) = find_next(document, heading, &["p", "div"]) {
        return cut(text_of(next).trim(), 200);
    }
    let Some(parent) = heading.parent().and_then(ElementRef::wrap) else {
        return String::new();
    };
    let parent_text = text_of(parent);
    let heading_text = text_of(heading);
    match parent_text.trim().strip_prefix(heading_text.trim()) {
        Some(rest) => cut(rest.trim(), 200),
        None => String::new(),
    }
}
