# feedgen

URLの内容を分析してRSSフィードを生成するツール。

## 機能

- Webページの内容を分析してRSS 2.0形式のフィードを生成
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