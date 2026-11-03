//! 記事・フィードの型と、RSS 2.0 への書き出し (docs/specs/models.md)。
//!
//! 仕様の M-1〜M-10 に従う。XML は手書きで組み立て、Python 版と要素の順序・自己閉じ・エスケープを揃える。

use chrono::{DateTime, FixedOffset};

/// RSS の記事 1 件。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RssItem {
    pub title: String,
    pub description: String,
    pub link: String,
    pub pub_date: Option<DateTime<FixedOffset>>,
    pub guid: Option<String>,
}

/// RSS のフィード (チャンネル + 記事)。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RssFeed {
    pub title: String,
    pub description: String,
    pub link: String,
    pub items: Vec<RssItem>,
}

const XML_HEAD: &str = concat!(
    "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n",
    "<rss version=\"2.0\" xmlns:atom=\"http://www.w3.org/2005/Atom\"><channel>",
);
const XML_TAIL: &str = "</channel></rss>";

impl RssFeed {
    /// RSS 2.0 の XML 文字列にする (M-2)。
    ///
    /// `now` は、日付を持つ記事がないときの `lastBuildDate` に使う現在時刻 (M-8)。
    pub fn to_xml(&self, now: DateTime<FixedOffset>) -> String {
        let last_build = self
            .items
            .iter()
            .filter_map(|item| item.pub_date)
            .max()
            .unwrap_or(now);

        let mut xml = String::from(XML_HEAD);
        push_element(&mut xml, "title", &self.title);
        push_element(&mut xml, "link", &self.link);
        push_element(&mut xml, "description", &self.description);
        push_element(&mut xml, "lastBuildDate", &format_date(last_build));
        for item in &self.items {
            item.push_xml(&mut xml);
        }
        xml.push_str(XML_TAIL);
        xml
    }
}

impl RssItem {
    fn push_xml(&self, xml: &mut String) {
        xml.push_str("<item>");
        push_element(xml, "title", &self.title);
        push_element(xml, "link", &self.link);
        push_element(xml, "description", &self.description);
        if let Some(date) = self.pub_date {
            push_element(xml, "pubDate", &format_date(date));
        }
        if let Some(guid) = &self.guid {
            push_element(xml, "guid", guid);
        }
        xml.push_str("</item>");
    }
}

/// `<name>text</name>` を足す。テキストが (整形後に) 空なら `<name/>` にする (M-4)。
fn push_element(xml: &mut String, name: &str, text: &str) {
    let escaped = escape(text);
    if escaped.is_empty() {
        xml.push_str(&format!("<{name}/>"));
    } else {
        xml.push_str(&format!("<{name}>{escaped}</{name}>"));
    }
}

/// `&` `<` `>` だけをエスケープし、XML 1.0 で使えない文字を取り除く (M-5、M-6)。
fn escape(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            c if is_invalid_xml_char(c) => {}
            c => out.push(c),
        }
    }
    out
}

fn is_invalid_xml_char(c: char) -> bool {
    matches!(c,
        '\u{0}'..='\u{8}' | '\u{b}' | '\u{c}' | '\u{e}'..='\u{1f}' | '\u{fffe}' | '\u{ffff}')
}

/// RFC 2822 風の日時。`to_rfc2822()` は日を 0 埋めしないので、書式を指定する (M-7)。
fn format_date(date: DateTime<FixedOffset>) -> String {
    date.format("%a, %d %b %Y %H:%M:%S %z").to_string()
}

#[cfg(test)]
mod tests;
