//! HTML パーサの golden テスト (docs/specs/parser.md 5 章)。
//!
//! tests/fixtures/ の HTML を解析し、Python 版の出力 (tools/gen_golden.py が生成した
//! *.expected.json) と一致することを確かめる。Python 版と挙動を変えた箇所 (P-3、P-4、P-6) は
//! ここでは比べず、src/parser/tests.rs に手書きの期待値を置いている。

use std::fs;
use std::path::PathBuf;

use chrono::{FixedOffset, TimeZone};
use feedgen_core::parser::parse;
use serde_json::Value;

fn fixture_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures")
}

fn read_json(path: PathBuf) -> Value {
    let text = fs::read_to_string(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()));
    serde_json::from_str(&text).unwrap_or_else(|e| panic!("{}: {e}", path.display()))
}

fn check(name: &str) {
    let dir = fixture_dir();
    let manifest = read_json(dir.join("manifest.json"));
    let entry = manifest
        .as_array()
        .expect("manifest は配列")
        .iter()
        .find(|e| e["name"] == name)
        .unwrap_or_else(|| panic!("manifest に {name} がない"));
    let base_url = entry["base_url"].as_str().expect("base_url");
    let max_items = entry["max_items"].as_u64().expect("max_items") as usize;
    let compare_description = entry["compare_description"].as_bool().unwrap_or(true);

    let html = fs::read_to_string(dir.join(format!("{name}.html"))).expect("HTML を読めない");
    let expected = read_json(dir.join(format!("{name}.expected.json")));
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

macro_rules! golden {
    ($($name:ident),+ $(,)?) => {
        $( #[test] fn $name() { check(stringify!($name)); } )+
    };
}

golden!(
    headings,
    get_text_exclusions,
    find_next_descendant,
    cards,
    card_titles,
    content_blocks,
    entities,
    dedupe_limit,
    meta_fallback,
    long_card,
    // `<noscript>` は要素として解析し、`<template>` の内側は文字列を空にする (P-1、P-2)
    noscript_card,
    noscript_heading,
    template_heading,
    template_description,
    // しきい値と件数の境界 (カードの 9/10 文字と 199/200/201 文字、ブロックの 29/30 文字、limit)
    cards_boundary,
    blocks_limit,
    blocks_threshold,
    headings_skip,
);
