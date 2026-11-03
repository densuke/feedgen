#!/usr/bin/env python
"""HTMLパーサの golden テスト用の期待値を、Python 版のパーサから生成する.

使い方:
    uv run python tools/gen_golden.py

crates/feedgen-core/tests/fixtures/manifest.json に載っている各フィクスチャ(HTML)を
Python 版の HTMLParser で解析し、結果を <name>.expected.json に書き出す。
manifest の detect が真のエントリは、既存フィードの検出結果(feeds)も書き出す。
pub_date は JSON に含めない(現在時刻になるため)。Rust 側のテストが
「pub_date が引数の now と一致すること」を別に確認する。
Python 版と挙動を変えた箇所(docs/specs/parser.md の P-3, P-4, P-6)は、
このオラクルでは検証せず、Rust 側のテストに手書きの期待値を置く。
"""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import feedgen.core.feed_detector as feed_detector
from feedgen.core.feed_detector import FeedDetector
from feedgen.core.parser import HTMLParser

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "crates" / "feedgen-core" / "tests" / "fixtures"


def detect_feeds(html: str, base_url: str) -> list[dict]:
    """HTMLの<link>から既存フィードを検出した結果を返す(Python 版の検出器、通信なし).

    検出器は取得を safe_request 経由で行うので、HTMLをそのまま返すものに差し替える。

    Args:
        html: 取得済みのHTML。
        base_url: 基準URL。

    Returns:
        検出結果(url, title, type)のリスト。
    """
    original = feed_detector.safe_request

    def stub(method, url, **kwargs):
        return SimpleNamespace(
            text=html, status_code=200, headers={}, raise_for_status=lambda: None
        )

    feed_detector.safe_request = stub
    try:
        return FeedDetector()._detect_from_html(base_url)
    finally:
        feed_detector.safe_request = original


def build_expected(html: str, base_url: str, max_items: int, detect: bool = False) -> dict:
    """1つのHTMLについて、Python 版パーサの出力を辞書にする.

    Args:
        html: 解析するHTML。
        base_url: 基準URL。
        max_items: 最大記事数。
        detect: 既存フィードの検出結果(feeds)も含めるか。

    Returns:
        メタデータと記事一覧を持つ辞書(detect が真なら feeds も)。
    """
    parser = HTMLParser()
    metadata = parser.parse_metadata(html, base_url)
    items = parser.extract_articles(html, base_url, max_items)
    expected = {
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
    if detect:
        expected["feeds"] = [
            {"url": feed["url"], "title": feed["title"], "type": feed["type"]}
            for feed in detect_feeds(html, base_url)
        ]
    return expected


def main() -> None:
    """マニフェストの全フィクスチャについて期待値を書き出す."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--real",
        action="store_true",
        help="実サイトのフィクスチャ(tests/fixtures/real/、gitignore 済み)を対象にする",
    )
    fixture_dir = FIXTURE_DIR / "real" if parser.parse_args().real else FIXTURE_DIR
    manifest = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest:
        html_name = entry.get("file", f"{entry['name']}.html")
        html = (fixture_dir / html_name).read_text(encoding="utf-8")
        expected = build_expected(
            html, entry["base_url"], entry["max_items"], entry.get("detect", False)
        )
        out_path = fixture_dir / f"{entry['name']}.expected.json"
        out_path.write_text(
            json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{entry['name']}: {len(expected['items'])} items")


if __name__ == "__main__":
    main()
