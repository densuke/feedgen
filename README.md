# feedgen

URLの内容を分析してRSSフィードを生成するツール。

## 機能

- 既存RSS/Atomフィードの自動検出・代理取得
- Webページの多戦略HTML解析によるRSS 2.0形式フィード生成
- TailwindCSS等のモダンサイト対応
- コマンドライン及び設定ファイルによる設定
- ライブラリとしても使用可能

## インストール

```bash
pip install -e .
```

## 使用方法

### コマンドライン

```bash
# 基本的な使用方法
feedgen https://example.com

# 既存フィード代理取得（推奨）
feedgen --use-feed https://example.com

# フィード検出優先
feedgen --feed-first https://example.com

# 設定ファイル指定
feedgen --config config.yaml https://example.com

# 出力ファイル指定
feedgen --output feed.xml https://example.com

# 最大記事数指定
feedgen --max-items 10 https://example.com
```

### ライブラリとして

```python
from feedgen.core import FeedGenerator

generator = FeedGenerator()
feed = generator.generate_feed("https://example.com")
print(feed.to_xml())
```

## 開発

```bash
# テスト実行
uv run pytest

# コード品質チェック
uv run ruff check
```