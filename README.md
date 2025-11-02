# feedgen

URLの内容を分析してRSSフィードを生成するツール。

## 機能

- 既存RSS/Atomフィードの自動検出・代理取得
- Webページの多戦略HTML解析によるRSS 2.0形式フィード生成
- TailwindCSS等のモダンサイト対応
- プラグイン型URL正規化システム（Google News、YouTube、Instagram等の特殊サイト対応）
- Google News URLデコード機能（実際のニュース記事URLへの変換）
- Instagram プロフィールページ対応
  - 軽量版: 認証不要でプロフィール情報取得
  - フル機能版: 認証ありで投稿詳細取得（instaloader使用）
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

# Google News URLキャッシュ機能
feedgen --decode-google-news --google-news-cache-ttl 7200 --google-news-cache-type memory https://news.google.com/topics/CAAqBwgKMKHL9QowkqbaAg

# Redisキャッシュ使用
feedgen --decode-google-news --google-news-cache-type redis https://news.google.com/topics/CAAqBwgKMKHL9QowkqbaAg

# Instagram プロフィールページ
feedgen https://www.instagram.com/username/
```

### Instagram対応について

Instagramプロフィールページから投稿情報を取得してRSSフィードを生成できます。

#### 軽量版（デフォルト）

認証不要でプロフィール情報のみ取得します。

- **対応URL**: プロフィールページのみ（例: `https://www.instagram.com/username/`）
- **取得情報**: プロフィール名、フォロワー数、フォロー数、投稿数、バイオ
- **制限事項**: 個別投稿の詳細は取得できません
- **認証**: 不要

```bash
# 軽量版の使用（デフォルト）
feedgen https://www.instagram.com/username/
```

#### フル機能版（要認証）

instaloaderライブラリを使用して投稿の詳細情報を取得します。

- **取得情報**: 投稿内容、いいね数、コメント数、投稿日時など
- **認証**: Instagram認証が必要
- **設定**: `config.yaml`で有効化

**インストール**:
```bash
uv add instaloader
# または
uv sync --extra instagram
```

**設定例** (`config.yaml`):
```yaml
instagram:
  use_full_client: true
  username: "あなたのユーザー名"
  session_file: "~/.config/instaloader/session-あなたのユーザー名"
  max_posts: 20
```

**認証手順の詳細**: [docs/instagram_setup.md](docs/instagram_setup.md)

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

# キャッシュ機能付き
curl "http://localhost:8000/feed?url=https://news.google.com/topics/CAAqBwgKMKHL9QowkqbaAg&decode_google_news=true&google_news_cache_ttl=7200&google_news_cache_type=memory"
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
from feedgen.core.cache import MemoryURLDecodeCache

decoder = GoogleNewsURLDecoder(request_interval=1)
google_news_url = "https://news.google.com/articles/CBMiSWh0dHBzOi8vd3d3LnRva3lvLW5wLmNvLmpwL2FydGljbGUvNTUwMDYw0gEA"
decoded_url = decoder.decode_url(google_news_url)
print(f"デコード結果: {decoded_url}")

# キャッシュ機能付きGoogle News URLデコーダー
cache = MemoryURLDecodeCache(max_size=1000, default_ttl=3600)
decoder_with_cache = GoogleNewsURLDecoder(request_interval=1, cache=cache)
decoded_url = decoder_with_cache.decode_url(google_news_url)
print(f"キャッシュ付きデコード結果: {decoded_url}")

# キャッシュ統計の確認
stats = cache.get_stats()
print(f"キャッシュ統計: ヒット={stats['hits']}, ミス={stats['misses']}, ヒット率={stats['hit_rate']:.2%}")

# Instagram プロフィール情報の取得（軽量版）
feed = generator.generate_feed("https://www.instagram.com/username/")
print(feed.to_xml())

# Instagram フル機能版の使用
from feedgen.core.instagram_client import InstagramFullClient

instagram_client = InstagramFullClient(
    username="あなたのユーザー名",
    session_file="~/.config/instaloader/session-あなたのユーザー名",
    max_posts=20
)
instagram_client.login()

generator = FeedGenerator(
    instagram_username="あなたのユーザー名",
    instagram_session_file="~/.config/instaloader/session-あなたのユーザー名",
    use_instagram_full_client=True
)
feed = generator.generate_feed("https://www.instagram.com/username/")
print(feed.to_xml())
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
  
  # キャッシュ設定（コスト削減と高速化のため）
  cache_enabled: true             # キャッシュ機能有効化（デフォルト: true）
  cache_type: memory              # キャッシュタイプ（memory/redis、デフォルト: memory）
  cache_ttl: 86400                # キャッシュ有効期限（秒、デフォルト: 24時間）
  cache_max_size: 1000            # メモリキャッシュ最大サイズ（デフォルト: 1000）
  redis_url: redis://localhost:6379/0  # Redis接続URL（Redisタイプ時のみ）
  redis_key_prefix: "feedgen:gnews:"   # Redisキープレフィックス（デフォルト）
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

### Google News URLキャッシュ機能

同じGoogle News URLが複数回デコードされる場合、キャッシュ機能によりAPI呼び出しを削減できます。

#### キャッシュのメリット

- **コスト削減**: 同じURLの重複デコードを回避
- **高速化**: キャッシュヒット時の即座な応答
- **レート制限回避**: API呼び出し頻度の削減

#### キャッシュタイプ

1. **メモリキャッシュ（memory）**
   - プロセス内のメモリに保存
   - 高速アクセス
   - プロセス終了時にクリア

2. **Redisキャッシュ（redis）**  
   - 外部Redisサーバーに保存
   - プロセス間で共有
   - 永続化可能

#### キャッシュ統計の確認

```python
from feedgen.core.cache import MemoryURLDecodeCache

cache = MemoryURLDecodeCache()
# ... URLデコード処理 ...

stats = cache.get_stats()
print(f"ヒット数: {stats['hits']}")
print(f"ミス数: {stats['misses']}")  
print(f"ヒット率: {stats['hit_rate']:.2%}")
print(f"キャッシュサイズ: {stats['size']}")
```

### 注意事項

- この機能は `googlenewsdecoder` ライブラリに依存しています
- デコード処理には時間がかかる場合があります（設定可能なリクエスト間隔による）
- レート制限やネットワークエラーに対するリトライ機能を内蔵しています
- デコードに失敗した場合は元のGoogle News URLが使用されます
- キャッシュ機能はデフォルトで有効ですが、設定で無効化可能です