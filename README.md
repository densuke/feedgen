# feedgen

URLの内容を分析してRSSフィードを生成するツール。

## 機能

- 既存RSS/Atomフィードの自動検出・代理取得
- Webページの多戦略HTML解析によるRSS 2.0形式フィード生成
- TailwindCSS等のモダンサイト対応
- プラグイン型URL正規化システム（Google News等の特殊サイト対応）
- Google News URLデコード機能（実際のニュース記事URLへの変換）
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

# Web API URL生成
feedgen --generate-url --api-host https://my-feedgen.com https://example.com

# 全オプション指定でのURL生成
feedgen --generate-url --api-host my-api.com --use-feed --max-items 5 https://blog.example.com

# Google News URLデコード機能
feedgen --decode-google-news https://news.google.com/topics/CAAqBwgKMKHL9QowkqbaAg

# デコード設定付き
feedgen --decode-google-news --google-news-interval 2 --google-news-timeout 15 https://news.google.com/topics/CAAqBwgKMKHL9QowkqbaAg

# 設定ファイルでのGoogle News機能有効化
feedgen --config config.yaml https://news.google.com/topics/CAAqBwgKMKHL9QowkqbaAg
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

# Google News URLデコード
curl "http://localhost:8000/feed?url=https://news.google.com/topics/CAAqBwgKMKHL9QowkqbaAg&decode_google_news=true"

# デコード設定付き
curl "http://localhost:8000/feed?url=https://news.google.com/topics/CAAqBwgKMKHL9QowkqbaAg&decode_google_news=true&google_news_interval=2"

# 複数の設定パラメータ指定
curl "http://localhost:8000/feed?url=https://news.google.com/topics/CAAqBwgKMKHL9QowkqbaAg&decode_google_news=true&google_news_interval=2&google_news_timeout=15&google_news_max_retries=5"
```

#### API仕様書

サーバー起動後、以下のURLでAPI仕様書を確認できます：
- **Swagger UI**: http://localhost:8000/docs  
- **ReDoc**: http://localhost:8000/redoc

### ライブラリとして

```python
from feedgen.core import FeedGenerator
from feedgen.core.google_news_decoder import GoogleNewsDecoderConfig

# 基本的な使用方法
generator = FeedGenerator()
feed = generator.generate_feed("https://example.com")
print(feed.to_xml())

# Google News URLデコード機能付き
config = GoogleNewsDecoderConfig(
    decode_enabled=True,
    request_interval=2,
    request_timeout=15
)
generator = FeedGenerator(google_news_config=config)
feed = generator.generate_feed("https://news.google.com/topics/CAAqBwgKMKHL9QowkqbaAg")
print(feed.to_xml())

# Google News URLデコーダーを直接使用
from feedgen.core.google_news_decoder import GoogleNewsURLDecoder

decoder = GoogleNewsURLDecoder(request_interval=1)
google_news_url = "https://news.google.com/articles/CBMiSWh0dHBzOi8vd3d3LnRva3lvLW5wLmNvLmpwL2FydGljbGUvNTUwMDYw0gEA"
decoded_url = decoder.decode_url(google_news_url)
print(f"デコード結果: {decoded_url}")
```

## 開発

```bash
# テスト実行
uv run pytest

# コード品質チェック
uv run ruff check
```

## 設定ファイル

設定ファイル例（config.example.yaml）:
```yaml
# フィード生成の基本設定
max_items: 20
cache_duration: 3600
user_agent: "feedgen/1.0"

# Web API設定（URL生成機能用） 
api_base_url: https://my-feedgen.example.com

# Google News URLデコード設定
google_news:
  decode_enabled: false           # デコード機能有効化（デフォルト: false）
  request_interval: 1             # リクエスト間隔（秒、デフォルト: 1）
  request_timeout: 10             # タイムアウト（秒、デフォルト: 10）
  max_retries: 3                  # 最大リトライ回数（デフォルト: 3）
  enable_logging: true            # デコードログ出力（デフォルト: true）
```

### URL生成機能

設定ファイルでapi_base_urlを設定すると、--api-hostオプションなしでURL生成ができます：

```bash
# 設定ファイル使用
feedgen --config config.yaml --generate-url https://example.com

# 出力例: https://my-feedgen.example.com/feed?url=https%3A%2F%2Fexample.com
```

## Google News URLデコード機能について

この機能は、Google News特有の暗号化されたURL（`https://news.google.com/articles/CBMi...`形式）を実際のニュース記事のURLに変換します。

### 動作例

```bash
# Google News URL（変換前）
https://news.google.com/articles/CBMiSWh0dHBzOi8vd3d3LnRva3lvLW5wLmNvLmpwL2FydGljbGUvNTUwMDYw0gEA

# デコード後の実際のURL例
https://www.tokyo-np.co.jp/article/550060
```

### 注意事項

- この機能は `googlenewsdecoder` ライブラリに依存しています
- デコード処理には時間がかかる場合があります（設定可能なリクエスト間隔による）
- レート制限やネットワークエラーに対するリトライ機能を内蔵しています
- デコードに失敗した場合は元のGoogle News URLが使用されます