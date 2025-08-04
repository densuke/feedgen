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

### Webサービス

```bash
# サーバー起動（簡単コマンド）
feedgen-serve

# サーバー起動（オプション指定）
feedgen-serve --host 0.0.0.0 --port 8000 --reload

# または直接起動
uv run uvicorn feedgen.api.main:app --host 0.0.0.0 --port 8000

# API呼び出し例
curl "http://localhost:8000/feed?url=https://example.com&use_feed=true"
```

#### API仕様書

サーバー起動後、以下のURLでAPI仕様書を確認できます：
- **Swagger UI**: http://localhost:8000/docs  
- **ReDoc**: http://localhost:8000/redoc

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