//! docs/specs/models.md 6 章のテスト表をテストにしたもの (RED)。
//!
//! 期待値は、Python 版 (`feedgenerator.Rss201rev2Feed`) の実際の出力に基づく。
//! 日時の `-0000` だけは、仕様 (M-7) に従って `+0000` に置き換えてある。

use chrono::{DateTime, FixedOffset, TimeZone};

use super::*;

// ---- 共通の道具 ----

fn dt(
    y: i32,
    mo: u32,
    d: u32,
    h: u32,
    mi: u32,
    s: u32,
    offset_hours: i32,
) -> DateTime<FixedOffset> {
    FixedOffset::east_opt(offset_hours * 3600)
        .expect("オフセットが不正")
        .with_ymd_and_hms(y, mo, d, h, mi, s)
        .single()
        .expect("日時が不正")
}

fn now() -> DateTime<FixedOffset> {
    dt(2026, 11, 3, 0, 20, 53, 0)
}

fn item(title: &str, description: &str, link: &str) -> RssItem {
    RssItem {
        title: title.into(),
        description: description.into(),
        link: link.into(),
        pub_date: None,
        guid: None,
    }
}

fn feed(items: Vec<RssItem>) -> RssFeed {
    RssFeed {
        title: "t".into(),
        description: "d".into(),
        link: "https://example.com/".into(),
        items,
    }
}

const HEAD: &str = concat!(
    "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n",
    "<rss version=\"2.0\" xmlns:atom=\"http://www.w3.org/2005/Atom\"><channel>",
);
const TAIL: &str = "</channel></rss>";

// ---- ケース A: 記事 2 件、日時あり (Python 版の実出力) ----

#[test]
fn case_a_two_items_matches_python_output() {
    let feed = RssFeed {
        title: "T & <b>\"title\"</b>".into(),
        description: "説明 あ & <p>x</p>\n改行".into(),
        link: "https://example.com/".into(),
        items: vec![
            RssItem {
                title: "記事1 & <x>".into(),
                description: "本文 \"q\" 'a' <b>".into(),
                link: "https://example.com/a?x=1&y=2".into(),
                pub_date: Some(dt(2026, 11, 3, 9, 30, 0, 0)),
                guid: Some("https://example.com/#heading-0".into()),
            },
            RssItem {
                title: "older".into(),
                description: "d".into(),
                link: "https://example.com/o".into(),
                pub_date: Some(dt(2026, 11, 1, 1, 2, 3, 0)),
                guid: Some("g2".into()),
            },
        ],
    };

    let expected = concat!(
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n",
        "<rss version=\"2.0\" xmlns:atom=\"http://www.w3.org/2005/Atom\"><channel>",
        "<title>T &amp; &lt;b&gt;\"title\"&lt;/b&gt;</title>",
        "<link>https://example.com/</link>",
        "<description>説明 あ &amp; &lt;p&gt;x&lt;/p&gt;\n改行</description>",
        "<lastBuildDate>Tue, 03 Nov 2026 09:30:00 +0000</lastBuildDate>",
        "<item><title>記事1 &amp; &lt;x&gt;</title>",
        "<link>https://example.com/a?x=1&amp;y=2</link>",
        "<description>本文 \"q\" 'a' &lt;b&gt;</description>",
        "<pubDate>Tue, 03 Nov 2026 09:30:00 +0000</pubDate>",
        "<guid>https://example.com/#heading-0</guid></item>",
        "<item><title>older</title><link>https://example.com/o</link>",
        "<description>d</description>",
        "<pubDate>Sun, 01 Nov 2026 01:02:03 +0000</pubDate>",
        "<guid>g2</guid></item>",
        "</channel></rss>",
    );
    assert_eq!(feed.to_xml(now()), expected);
}

// ---- ケース B: オフセットの保持 ----

#[test]
fn case_b_offset_is_preserved() {
    let mut aware = item("aware", "d", "https://example.com/b");
    aware.pub_date = Some(dt(2026, 11, 3, 9, 30, 0, 9));
    aware.guid = Some("g-aware".into());

    let expected = format!(
        "{HEAD}<title>t</title><link>https://example.com/</link><description>d</description>\
         <lastBuildDate>Tue, 03 Nov 2026 09:30:00 +0900</lastBuildDate>\
         <item><title>aware</title><link>https://example.com/b</link><description>d</description>\
         <pubDate>Tue, 03 Nov 2026 09:30:00 +0900</pubDate><guid>g-aware</guid></item>{TAIL}"
    );
    assert_eq!(feed(vec![aware]).to_xml(now()), expected);
}

// ---- ケース C: 日付・guid なし。空の description は自己閉じ ----

#[test]
fn case_c_item_without_date_and_guid() {
    let bare = item("no guid / no date", "", "https://example.com/c");

    let expected = format!(
        "{HEAD}<title>t</title><link>https://example.com/</link><description>d</description>\
         <lastBuildDate>Tue, 03 Nov 2026 00:20:53 +0000</lastBuildDate>\
         <item><title>no guid / no date</title><link>https://example.com/c</link><description/></item>{TAIL}"
    );
    assert_eq!(feed(vec![bare]).to_xml(now()), expected);
}

// ---- ケース D: 記事なし ----

#[test]
fn case_d_empty_feed_uses_now() {
    let empty = RssFeed {
        title: "t".into(),
        description: "".into(),
        link: "https://example.com/".into(),
        items: vec![],
    };

    let expected = format!(
        "{HEAD}<title>t</title><link>https://example.com/</link><description/>\
         <lastBuildDate>Tue, 03 Nov 2026 00:20:53 +0000</lastBuildDate>{TAIL}"
    );
    assert_eq!(empty.to_xml(now()), expected);
}

// ---- ケース E: XML 1.0 で使えない文字は除去し、他の記事を巻き込まない ----

#[test]
fn case_e_invalid_xml_characters_are_removed() {
    let bad = item(
        "a\u{1}b\u{b}c\u{fffe}d é",
        "x\u{0}y",
        "https://example.com/bad",
    );
    let tab = item("tab\there\nline", "ok", "https://example.com/ok");

    let xml = feed(vec![bad, tab]).to_xml(now());

    assert!(xml.contains("<title>abcd é</title>"), "{xml}");
    assert!(xml.contains("<description>xy</description>"), "{xml}");
    // 許可される制御文字 (タブ、改行) は残る
    assert!(xml.contains("<title>tab\there\nline</title>"), "{xml}");
    assert!(
        !xml.contains(['\u{1}', '\u{b}', '\u{0}', '\u{fffe}']),
        "{xml}"
    );
}

// ---- ケース F: lastBuildDate は記事の日時の最大値 ----

#[test]
fn case_f_last_build_date_is_the_latest_item_date() {
    let mut old = item("old", "d", "https://example.com/1");
    old.pub_date = Some(dt(2026, 11, 1, 0, 0, 0, 0));
    let undated = item("undated", "d", "https://example.com/2");
    let mut new = item("new", "d", "https://example.com/3");
    new.pub_date = Some(dt(2026, 11, 2, 12, 0, 0, 0));

    let xml = feed(vec![old, undated, new]).to_xml(now());
    assert!(
        xml.contains("<lastBuildDate>Mon, 02 Nov 2026 12:00:00 +0000</lastBuildDate>"),
        "{xml}"
    );
}

#[test]
fn case_f_latest_is_chosen_by_instant_and_keeps_its_own_offset() {
    // 09:30 +0900 は 00:30 UTC。02:00 +0000 の方が新しい。
    let mut jst = item("jst", "d", "https://example.com/1");
    jst.pub_date = Some(dt(2026, 11, 3, 9, 30, 0, 9));
    let mut utc = item("utc", "d", "https://example.com/2");
    utc.pub_date = Some(dt(2026, 11, 3, 2, 0, 0, 0));

    let xml = feed(vec![jst, utc]).to_xml(now());
    assert!(
        xml.contains("<lastBuildDate>Tue, 03 Nov 2026 02:00:00 +0000</lastBuildDate>"),
        "{xml}"
    );
}

// ---- ケース G: 日は 0 埋め ----

#[test]
fn case_g_day_is_zero_padded() {
    let mut early = item("early", "d", "https://example.com/1");
    early.pub_date = Some(dt(2026, 1, 5, 0, 0, 0, 0));

    let xml = feed(vec![early]).to_xml(now());
    assert!(
        xml.contains("<pubDate>Mon, 05 Jan 2026 00:00:00 +0000</pubDate>"),
        "{xml}"
    );
}

// ---- ケース H: エスケープは & < > のみ ----

#[test]
fn case_h_only_ampersand_and_angle_brackets_are_escaped() {
    let tricky = item("\"a\" 'b' & <c> >", "d", "https://example.com/1");

    let xml = feed(vec![tricky]).to_xml(now());
    assert!(
        xml.contains("<title>\"a\" 'b' &amp; &lt;c&gt; &gt;</title>"),
        "{xml}"
    );
}

// ---- M-4: 空の title も自己閉じ ----

#[test]
fn empty_title_is_self_closing() {
    let xml = feed(vec![item("", "d", "https://example.com/1")]).to_xml(now());
    assert!(xml.contains("<item><title/><link>"), "{xml}");
}

// ---- M-9: 入力の順序のまま出す ----

#[test]
fn items_keep_their_given_order() {
    let items = ["c", "a", "b"]
        .map(|t| item(t, "d", "https://example.com/x"))
        .to_vec();

    let xml = feed(items).to_xml(now());
    let pos = |t: &str| {
        xml.find(&format!("<title>{t}</title>"))
            .expect("記事がない")
    };
    assert!(pos("c") < pos("a") && pos("a") < pos("b"), "{xml}");
}
