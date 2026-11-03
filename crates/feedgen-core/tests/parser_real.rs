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
