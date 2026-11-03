//! 文字列の取り出しと、木の探索の小さな道具 (docs/specs/parser.md P-2、2.3、2.4)。

use scraper::{ElementRef, Html, Node, Selector};

/// `get_text()` から外す要素 (Python 版 BeautifulSoup の挙動)。
const EXCLUDED: [&str; 5] = ["script", "style", "template", "rt", "rp"];

/// 子孫のテキストを区切りなしで連結する。`EXCLUDED` の中身とコメントは含めない (P-2)。
pub(super) fn text_of(element: ElementRef) -> String {
    let mut out = String::new();
    push_text(element, &mut out);
    out
}

fn push_text(element: ElementRef, out: &mut String) {
    for child in element.children() {
        if let Some(child_element) = ElementRef::wrap(child) {
            if !EXCLUDED.contains(&child_element.value().name()) {
                push_text(child_element, out);
            }
        } else if let Node::Text(text) = child.value() {
            out.push_str(text);
        }
    }
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
