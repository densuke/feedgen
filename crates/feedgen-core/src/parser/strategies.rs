//! 記事を取り出す 3 つの戦略 (docs/specs/parser.md 2.2、P-4)。

use chrono::{DateTime, FixedOffset};
use scraper::{ElementRef, Html};

use super::link::{first_anchor_link, first_href_link, normalize};
use super::text::{cut, first_chars, first_descendant, heading_description, selector, text_of};
use crate::models::RssItem;

const HEADINGS: [&str; 6] = ["h1", "h2", "h3", "h4", "h5", "h6"];
const CARD_SELECTORS: [&str; 5] = [
    r#"[class*="content"]"#,
    r#"[class*="card"]"#,
    r#"[class*="cursor-pointer"]"#,
    "article",
    r#"[class*="item"]"#,
];
const DATA_LINK_ATTRS: [&str; 3] = ["data-href", "data-url", "data-link"];

pub(super) struct Strategies<'a> {
    pub document: &'a Html,
    pub base_url: &'a str,
    pub now: DateTime<FixedOffset>,
}

impl Strategies<'_> {
    fn item(
        &self,
        title: String,
        description: String,
        link: String,
        kind: &str,
        number: usize,
    ) -> RssItem {
        RssItem {
            title,
            description,
            link,
            pub_date: Some(self.now),
            // `guid` の番号づけは Python 版のまま (docs/specs/parser.md 0 章の例外)。
            guid: Some(format!("{}#{kind}-{number}", self.base_url)),
        }
    }

    /// 戦略 1: 見出し。`guid` の番号は、対象にした見出しの文書順の番号 (捨てたものも数える)。
    pub fn headings(&self, max_items: usize) -> Vec<RssItem> {
        let mut items = Vec::new();
        let selector = selector(&HEADINGS.join(", "));
        for (number, heading) in self
            .document
            .select(&selector)
            .take(max_items * 2)
            .enumerate()
        {
            if items.len() >= max_items {
                break;
            }
            let Some(link) = first_href_link(heading, self.base_url) else {
                continue;
            };
            let title = text_of(heading).trim().to_string();
            if title.is_empty() {
                continue;
            }
            let description = heading_description(self.document, heading);
            items.push(self.item(title, description, link, "heading", number));
        }
        items
    }

    /// 戦略 2: カード。`remaining` は不足している件数。
    pub fn cards(&self, remaining: usize) -> Vec<RssItem> {
        let mut items = Vec::new();
        for css in CARD_SELECTORS {
            if items.len() >= remaining {
                break;
            }
            for card in self.document.select(&selector(css)).take(remaining * 2) {
                if items.len() >= remaining {
                    break;
                }
                let text = text_of(card);
                let text = text.trim();
                if text.chars().count() < 10 {
                    continue;
                }
                let title = card_title(card, text);
                if title.is_empty() {
                    continue;
                }
                let link = card_link(card, self.base_url);
                if link.is_none() && title.chars().count() <= 5 {
                    continue;
                }
                let link = link.unwrap_or_else(|| self.base_url.to_string());
                let number = items.len();
                items.push(self.item(title, cut(text, 200), link, "card", number));
            }
        }
        items
    }

    /// 戦略 3: コンテンツブロック (最後の手段)。`guid` の番号は対象にしたブロックの番号。
    pub fn blocks(&self, remaining: usize) -> Vec<RssItem> {
        let mut items = Vec::new();
        for (number, block) in self
            .document
            .select(&selector("p, div"))
            .take(remaining * 3)
            .enumerate()
        {
            if items.len() >= remaining {
                break;
            }
            let text = text_of(block);
            let text = text.trim();
            if text.chars().count() < 30 {
                continue;
            }
            let Some(link) = first_anchor_link(block, self.base_url) else {
                continue;
            };
            let first_line = text.split('\n').next().unwrap_or("");
            let title = first_chars(first_line, 100);
            items.push(self.item(title, cut(text, 200), link, "content", number));
        }
        items
    }
}

/// カードのタイトル。子孫の見出し、なければ 5 文字より長く 200 文字より短い最初の行、
/// それもなければ先頭 100 文字。
fn card_title(card: ElementRef, text: &str) -> String {
    if let Some(heading) = first_descendant(card, &HEADINGS) {
        return text_of(heading).trim().to_string();
    }
    for line in text.split('\n') {
        let line = line.trim();
        let length = line.chars().count();
        if length > 5 && length < 200 {
            return line.to_string();
        }
    }
    if text.chars().count() > 100 {
        format!("{}...", first_chars(text, 100))
    } else {
        text.to_string()
    }
}

/// カードのリンク。最初の `<a>` の `href` が空でなければそれ。そうでなければ、
/// カード自身の `data-href` / `data-url` / `data-link` の順。
fn card_link(card: ElementRef, base_url: &str) -> Option<String> {
    if let Some(anchor) = first_descendant(card, &["a"])
        && let Some(href) = anchor.value().attr("href").filter(|h| !h.is_empty())
    {
        return normalize(href, base_url);
    }
    DATA_LINK_ATTRS
        .iter()
        .find_map(|attr| card.value().attr(attr).filter(|v| !v.is_empty()))
        .and_then(|value| normalize(value, base_url))
}
