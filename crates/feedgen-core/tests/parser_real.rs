//! 実サイトの HTML を Python 版と比べるテスト (docs/specs/parser.md 5 章 3)。
//!
//! `tests/fixtures/real/` は他人のサイトの本文なので、コミットしない (.gitignore 済み)。
//! ディレクトリがなければ、このテストは何もせずに通る。
//!
//! 手順 (手元で実行する):
//!   1. `tests/fixtures/real/` に HTML と `manifest.json` を置く
//!   2. `uv run python tools/gen_golden.py --real` で期待値を生成する
//!   3. `cargo test -p feedgen-core --test parser_real`

mod common;

use std::path::PathBuf;

#[test]
fn real_sites_match_python() {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/real");
    let manifest_path = dir.join("manifest.json");
    if !manifest_path.exists() {
        eprintln!("tests/fixtures/real/ がないので、実サイトのテストを飛ばす");
        return;
    }
    let manifest = common::read_json(&manifest_path);
    for entry in manifest.as_array().expect("manifest は配列") {
        common::check_entry(&dir, entry);
    }
}

/// 実サイトの RDF (RSS 1.0) は、ルート要素でフィードと判定され、HTML のページは判定されない
/// (docs/specs/detector.md D-5。pipeline.md G-7 の本番の発見)。
#[test]
fn real_rdf_is_a_feed_and_real_html_is_not() {
    use feedgen_core::detector::{RootKind, feed_root, proxied_content_type};

    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/real");
    let rdf_path = dir.join("real_wor.rdf");
    if !rdf_path.exists() {
        eprintln!("tests/fixtures/real/real_wor.rdf がないので、飛ばす");
        return;
    }
    let rdf = std::fs::read(&rdf_path).expect("RDF を読めない");
    assert_eq!(feed_root(&rdf), Some(RootKind::Rdf));
    assert_eq!(
        proxied_content_type(RootKind::Rdf, "application/xml"),
        "application/rss+xml"
    );

    for name in ["real_mfujin.html", "real_kabumatome.html"] {
        let html = std::fs::read(dir.join(name)).expect("HTML を読めない");
        assert_eq!(feed_root(&html), None, "{name}");
    }
}
