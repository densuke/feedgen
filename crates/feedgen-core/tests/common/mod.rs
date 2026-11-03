//! HTML パーサの golden テストの共通部品 (docs/specs/parser.md 5 章)。
//!
//! マニフェストの 1 件 (HTML のファイル名・基準 URL・最大件数) について、HTML を解析し、
//! Python 版の出力 (tools/gen_golden.py が生成した `<name>.expected.json`) と比べる。

use std::fs;
use std::path::Path;

use chrono::{FixedOffset, TimeZone};
use feedgen_core::parser::parse;
use serde_json::Value;

pub fn read_json(path: &Path) -> Value {
    let text = fs::read_to_string(path).unwrap_or_else(|e| panic!("{}: {e}", path.display()));
    serde_json::from_str(&text).unwrap_or_else(|e| panic!("{}: {e}", path.display()))
}

/// `dir` にある HTML を解析し、期待値と一致することを確かめる。
///
/// `compare_description` が偽のエントリは、チャンネルの説明を比べない (P-3 で直した挙動のため)。
pub fn check_entry(dir: &Path, entry: &Value) {
    let name = entry["name"].as_str().expect("name");
    let html_name = entry["file"]
        .as_str()
        .map_or_else(|| format!("{name}.html"), str::to_string);
    let base_url = entry["base_url"].as_str().expect("base_url");
    let max_items = entry["max_items"].as_u64().expect("max_items") as usize;
    let compare_description = entry["compare_description"].as_bool().unwrap_or(true);

    let html = fs::read_to_string(dir.join(&html_name)).expect("HTML を読めない");
    let expected = read_json(&dir.join(format!("{name}.expected.json")));
    let now = FixedOffset::east_opt(0)
        .expect("オフセットが不正")
        .with_ymd_and_hms(2026, 11, 3, 0, 0, 0)
        .single()
        .expect("日時が不正");

    let (metadata, items) = parse(&html, base_url, max_items, now);

    let meta = &expected["metadata"];
    assert_eq!(
        metadata.title,
        meta["title"].as_str().unwrap(),
        "{name}: title"
    );
    assert_eq!(
        metadata.link,
        meta["link"].as_str().unwrap(),
        "{name}: link"
    );
    if compare_description {
        assert_eq!(
            metadata.description,
            meta["description"].as_str().unwrap(),
            "{name}: description"
        );
    }

    let expected_items = expected["items"].as_array().expect("items は配列");
    let got_titles: Vec<&str> = items.iter().map(|i| i.title.as_str()).collect();
    assert_eq!(
        items.len(),
        expected_items.len(),
        "{name}: 件数 (実際: {got_titles:?})"
    );
    for (n, (got, want)) in items.iter().zip(expected_items).enumerate() {
        let at = format!("{name}[{n}]");
        assert_eq!(got.title, want["title"].as_str().unwrap(), "{at}: title");
        assert_eq!(
            got.description,
            want["description"].as_str().unwrap(),
            "{at}: description"
        );
        assert_eq!(got.link, want["link"].as_str().unwrap(), "{at}: link");
        assert_eq!(got.guid.as_deref(), want["guid"].as_str(), "{at}: guid");
        assert_eq!(got.pub_date, Some(now), "{at}: pub_date は now (P-5)");
    }
}
