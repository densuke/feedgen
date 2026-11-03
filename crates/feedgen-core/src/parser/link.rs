//! リンクの解決 (docs/specs/parser.md P-6)。

use scraper::ElementRef;
use url::Url;

use super::text::first_descendant;

/// `href` を基準 URL に対して解決する。http / https 以外になるものは `None` (リンクなし)。
pub(super) fn normalize(href: &str, base_url: &str) -> Option<String> {
    let joined = Url::parse(base_url).ok()?.join(href).ok()?;
    matches!(joined.scheme(), "http" | "https").then(|| joined.to_string())
}

/// 子孫の最初の `<a>` の、空でない `href` を解決したもの。
///
/// 最初の `<a>` の `href` が空でも次の `<a>` を探す戦略 1 の規則 (P-4)。
pub(super) fn first_href_link(element: ElementRef, base_url: &str) -> Option<String> {
    let anchor = super::text::descendant_elements(element).find(|e| {
        e.value().name() == "a" && e.value().attr("href").is_some_and(|h| !h.is_empty())
    })?;
    normalize(anchor.value().attr("href")?, base_url)
}

/// 子孫の最初の `<a>` の `href` が空でなければ、それを解決したもの。
///
/// 最初の `<a>` の `href` が空なら、次の `<a>` は探さない (戦略 2、3 の規則。Python 版と同じ)。
pub(super) fn first_anchor_link(element: ElementRef, base_url: &str) -> Option<String> {
    let anchor = first_descendant(element, &["a"])?;
    let href = anchor.value().attr("href").filter(|h| !h.is_empty())?;
    normalize(href, base_url)
}
