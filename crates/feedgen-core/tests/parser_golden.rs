//! HTML パーサの golden テスト (docs/specs/parser.md 5 章)。
//!
//! tests/fixtures/ の HTML を解析し、Python 版の出力 (tools/gen_golden.py が生成した
//! *.expected.json) と一致することを確かめる。Python 版と挙動を変えた箇所 (P-3、P-4、P-6) は
//! ここでは比べず、src/parser/tests.rs に手書きの期待値を置いている。

mod common;

use std::path::PathBuf;

fn fixture_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures")
}

fn check(name: &str) {
    let dir = fixture_dir();
    let manifest = common::read_json(&dir.join("manifest.json"));
    let entry = manifest
        .as_array()
        .expect("manifest は配列")
        .iter()
        .find(|e| e["name"] == name)
        .unwrap_or_else(|| panic!("manifest に {name} がない"));
    common::check_entry(&dir, entry);
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
    // 空白だけのテキストは短くまとめられる (BeautifulSoup の挙動。実サイトで発見。2.3)
    whitespace_indent,
    whitespace_special,
);
