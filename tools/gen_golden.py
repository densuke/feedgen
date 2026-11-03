#!/usr/bin/env python
"""HTMLパーサの golden テスト用の期待値を、Python 版のパーサから生成する.

使い方:
    uv run python tools/gen_golden.py

crates/feedgen-core/tests/fixtures/manifest.json に載っている各フィクスチャ(HTML)を
Python 版の HTMLParser で解析し、結果を <name>.expected.json に書き出す。
pub_date は JSON に含めない(現在時刻になるため)。Rust 側のテストが
「pub_date が引数の now と一致すること」を別に確認する。
Python 版と挙動を変えた箇所(docs/specs/parser.md の P-3, P-4, P-6)は、
このオラクルでは検証せず、Rust 側のテストに手書きの期待値を置く。
"""

import json
from pathlib import Path

from feedgen.core.parser import HTMLParser

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "crates" / "feedgen-core" / "tests" / "fixtures"


def build_expected(html: str, base_url: str, max_items: int) -> dict:
    """1つのHTMLについて、Python 版パーサの出力を辞書にする.

    Args:
        html: 解析するHTML。
        base_url: 基準URL。
        max_items: 最大記事数。

    Returns:
        メタデータと記事一覧を持つ辞書。
    """
    parser = HTMLParser()
    metadata = parser.parse_metadata(html, base_url)
    items = parser.extract_articles(html, base_url, max_items)
    return {
        "metadata": metadata,
        "items": [
            {
                "title": item.title,
                "description": item.description,
                "link": item.link,
                "guid": item.guid,
            }
            for item in items
        ],
    }


def main() -> None:
    """マニフェストの全フィクスチャについて期待値を書き出す."""
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest:
        html = (FIXTURE_DIR / f"{entry['name']}.html").read_text(encoding="utf-8")
        expected = build_expected(html, entry["base_url"], entry["max_items"])
        out_path = FIXTURE_DIR / f"{entry['name']}.expected.json"
        out_path.write_text(
            json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{entry['name']}: {len(expected['items'])} items")


if __name__ == "__main__":
    main()
