# feedgen 仕様書（EARS表記法）

## システム概要

URLの内容を分析してRSS Feedを生成するシステム。
コアライブラリ、CLI版、Web API版の3層構造で実装する。

## コアライブラリ（feedgen.core）

### 既存フィード検出機能

**Event**: URLが指定されたとき
**Actor**: FeedDetectorクラス
**Response**: 指定されたURLに既存のRSS/Atomフィードが存在するかを検出し、発見した場合は代理取得する
**System**: feedgen.core.FeedDetector

#### 詳細動作

1. HTMLのlinkタグ（rel="alternate"）からフィードを検出
2. 一般的なフィードパス（/feed, /rss, /atom.xml等）を確認
3. 発見したフィードの取得・配信

#### 対応フィード形式

- RSS 2.0（application/rss+xml）
- Atom（application/atom+xml）
- JSON Feed（application/json）

### Feed生成機能

**Event**: URLが指定されたとき（既存フィードが見つからない場合）
**Actor**: FeedGeneratorクラス
**Response**: 指定されたURLの内容を分析し、RSS形式のフィードを生成する
**System**: feedgen.core.FeedGenerator

#### 詳細動作

1. URLからWebページを取得
2. 多戦略HTML解析でメタデータと記事一覧を抽出：
   - 見出しタグ戦略（h1〜h6内のリンク）
   - カード要素戦略（TailwindCSS等のモダンサイト対応）
   - コンテンツブロック戦略（フォールバック用）
3. プラグイン型URL正規化システムでリンクURLを正規化
4. 重複記事の排除（タイトルベース）
5. RSS 2.0形式のXMLを生成

#### 入力

- `url: str` - 分析対象のURL
- `config: Optional[Dict]` - 設定オプション
  - `max_items: int` - 最大記事数（デフォルト: 20）
  - `cache_duration: int` - キャッシュ有効時間（秒、デフォルト: 3600）

#### 出力

- `RSSFeed` - RSS形式のフィードオブジェクト
  - `to_xml() -> str` - XML文字列として出力
  - `to_dict() -> Dict` - 辞書形式として出力

#### エラーハンドリング

**Event**: URL取得に失敗したとき
**Actor**: FeedGeneratorクラス
**Response**: FeedGenerationErrorを発生させる
**System**: feedgen.core.exceptions

**Event**: HTML解析に失敗したとき
**Actor**: FeedGeneratorクラス
**Response**: ParseErrorを発生させる
**System**: feedgen.core.exceptions

### URL正規化機能

**Event**: HTML解析中に相対URLや特殊なURL形式が検出されたとき
**Actor**: URLNormalizerRegistry、各種URLNormalizerクラス
**Response**: サイト固有のルールに従ってURLを正規化し、絶対URLに変換する
**System**: feedgen.core.url_normalizers

#### 詳細動作

1. HTMLパーサーがリンクを検出
2. URLNormalizerRegistryが適切なNormalizerを選択
3. サイト固有の正規化ルールを適用：
   - Google News: `./articles/`、`./read/` 形式を `https://news.google.com/` に変換
   - 一般サイト: 標準的な相対URL→絶対URL変換
4. 正規化されたURLを返却

#### 対応サイト

- **Google News** (`news.google.com`)
  - `./articles/[ID]` → `https://news.google.com/articles/[ID]`
  - `./read/[ID]` → `https://news.google.com/read/[ID]`
  - `/topics/[ID]` → `https://news.google.com/topics/[ID]`
- **一般サイト** (フォールバック)
  - 標準的な相対URL→絶対URL変換

#### 拡張性

新しいサイト対応はURLNormalizerクラスを継承して追加するだけで実現可能。既存コードへの影響なし。

### YouTube検索機能

**Event**: YouTube検索URLが指定されたとき
**Actor**: YouTubeAPIClientクラス
**Response**: YouTube Data API v3を使用して検索結果を取得し、RSS形式で返却する
**System**: feedgen.core.youtube_client

#### 詳細動作

1. YouTube検索URLからクエリパラメータを抽出
2. YouTube Data API v3のsearch.listエンドポイントを呼び出し
3. 検索結果（動画情報）を取得：
   - タイトル、説明、チャンネル名
   - 投稿日、サムネイルURL
   - 動画URL（watch?v=形式）
4. 取得した情報をRSSItemオブジェクトに変換
5. RSS形式のフィードとして返却

#### 対応URL形式

- `https://www.youtube.com/results?search_query=[検索クエリ]`
- `https://www.youtube.com/results?search_query=[クエリ]&sp=[フィルタ]`

#### API仕様

- **エンドポイント**: YouTube Data API v3 search.list
- **必須パラメータ**: part="snippet"
- **クォータ消費**: 100単位/リクエスト
- **制限**: maxResults=50（最大50件）
- **認証**: API Key必須

#### 設定要件

- YouTube Data API v3のAPI Keyが必要
- 無料枠: 1日10,000クォータ（100回検索相当）
- 設定ファイルまたは環境変数でAPI Key指定

#### エラーハンドリング

**Event**: API Key未設定またはクォータ超過時
**Actor**: YouTubeAPIClientクラス
**Response**: YouTubeAPIErrorを発生させ、HTMLパーサーにフォールバック
**System**: feedgen.core.exceptions

**Event**: API呼び出し失敗時
**Actor**: YouTubeAPIClientクラス
**Response**: ネットワークエラーとして処理し、HTMLパーサーにフォールバック
**System**: feedgen.core.exceptions

### Web API URL生成機能

**Event**: Web APIのフィードURLが必要なとき
**Actor**: URLGeneratorクラス
**Response**: 指定されたパラメータでWeb API用のフィードURLを生成する
**System**: feedgen.core.URLGenerator

#### 詳細動作

1. ベースURLの正規化（プロトコル自動付加、末尾スラッシュ除去）
2. URLの妥当性検証
3. パラメータのURLエンコーディング
4. クエリパラメータ組み立てと完全URL生成

#### 入力

- `api_base_url: str` - Web APIのベースURL
- `target_url: str` - 分析対象のURL
- `max_items: Optional[int]` - 最大記事数
- `use_feed: Optional[bool]` - 既存フィード代理取得
- `feed_first: Optional[bool]` - フィード検出優先
- `user_agent: Optional[str]` - User-Agentヘッダー

#### 出力

- `str` - 生成されたWeb API URL（例: `https://api.example.com/feed?url=https%3A%2F%2Fexample.com&use_feed=true`）

## CLI版（feedgen.cli）

### コマンドライン実行機能

**Event**: コマンドライン引数でURLが指定されたとき
**Actor**: CLIインターフェース
**Response**: コアライブラリを使用してRSSフィードを生成し、標準出力に出力する
**System**: feedgen.cli.main

#### 使用方法

```bash
# 基本的な使用方法
feedgen https://example.com

# 設定ファイル指定
feedgen --config config.yaml https://example.com

# 出力ファイル指定
feedgen --output feed.xml https://example.com

# 最大記事数指定
feedgen --max-items 10 https://example.com

# 既存フィード代理取得
feedgen --use-feed https://example.com

# フィード検出優先（見つからない場合のみHTML解析）
feedgen --feed-first https://example.com

# User-Agent指定
feedgen --user-agent "custom-agent/1.0" https://example.com

# Web API URL生成
feedgen --generate-url --api-host https://my-feedgen.com https://example.com

# 全オプション指定でのURL生成
feedgen --generate-url --api-host my-api.com --use-feed --max-items 5 https://blog.example.com
```

### Web API URL生成機能

**Event**: --generate-urlオプションが指定されたとき
**Actor**: CLIインターフェース
**Response**: Web API用のフィードURLを生成して出力する
**System**: feedgen.cli.main

#### 使用方法

```bash
# APIホスト指定でのURL生成
feedgen --generate-url --api-host https://my-feedgen.com https://example.com

# 設定ファイルのapi_base_url使用
feedgen --config config.yaml --generate-url https://example.com

# ファイル出力
feedgen --generate-url --api-host my-api.com --output api-url.txt https://example.com
```

#### 設定ファイル

**Event**: --configオプションで設定ファイルが指定されたとき
**Actor**: 設定ローダー
**Response**: YAML形式の設定ファイルを読み込み、オプションを適用する
**System**: feedgen.cli.config

設定ファイル例（config.yaml）:
```yaml
max_items: 20
cache_duration: 3600
output_format: xml
user_agent: "feedgen/1.0"
api_base_url: https://my-feedgen.example.com  # Web API URL生成用
```

## Web API版

### HTTP API機能

**Event**: GETリクエストでURLパラメータが指定されたとき
**Actor**: Web APIサーバー
**Response**: 既存フィード検出または新規生成でRSSフィードを返却する
**System**: feedgen.api.main

#### APIエンドポイント

```
GET /feed?url=<target_url>&max_items=<number>&use_feed=<boolean>&feed_first=<boolean>&user_agent=<string>
```

#### パラメータ

- `url` (必須): 分析対象のURL
- `max_items` (オプション): 最大記事数（デフォルト: 20）
- `use_feed` (オプション): 既存フィード代理取得（true/false、デフォルト: false）
- `feed_first` (オプション): フィード検出優先（true/false、デフォルト: false）
- `user_agent` (オプション): User-Agentヘッダー

#### レスポンス形式

- **成功時**: 
  - Content-Type: application/rss+xml
  - RSS 2.0形式のXML
- **エラー時**: 
  - Content-Type: application/json
  - `{"error": "エラーメッセージ"}`

#### 使用例

```bash
# 基本的な使用方法
curl "http://localhost:8000/feed?url=https://example.com"

# 既存フィード代理取得
curl "http://localhost:8000/feed?url=https://example.com&use_feed=true"

# フィード検出優先
curl "http://localhost:8000/feed?url=https://example.com&feed_first=true"
```

### Web APIサーバー起動

**Event**: feedgen-serveコマンドが実行されたとき
**Actor**: WebAPIサーバー起動コマンド
**Response**: FastAPI WebサーバーをUvicornで起動する
**System**: feedgen.cli.webapi

#### 使用方法

```bash
# 基本起動
feedgen-serve

# ホスト・ポート指定
feedgen-serve --host 0.0.0.0 --port 8080

# 開発モード（自動リロード）
feedgen-serve --reload
```

## 技術仕様

### 必要なライブラリ

- `requests`: HTTP通信
- `beautifulsoup4`: HTML解析
- `feedgenerator`: RSS生成
- `pydantic`: データバリデーション
- `click`: CLI構築
- `pyyaml`: 設定ファイル処理
- `fastapi`: Web API構築
- `uvicorn`: ASGI Webサーバー
- `google-api-python-client`: YouTube Data API v3アクセス
- `pytest`: テスト実行
- `httpx`: HTTPテスト用クライアント
- `ruff`: コード品質チェック

### プロジェクト構造

```
feedgen/
├── feedgen/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── generator.py      # FeedGeneratorクラス
│   │   ├── feed_detector.py  # 既存フィード検出クラス
│   │   ├── url_generator.py  # Web API URL生成クラス
│   │   ├── url_normalizers.py # URL正規化システム（プラグイン型）
│   │   ├── youtube_client.py # YouTube Data API v3クライアント
│   │   ├── parser.py         # HTML解析機能（多戦略）
│   │   ├── models.py         # データモデル（RSSFeed, RSSItem）
│   │   └── exceptions.py     # 例外クラス（FeedGenerationError, ParseError）
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── main.py          # CLIメイン処理
│   │   ├── webapi.py        # Web APIサーバー起動
│   │   └── config.py        # 設定管理
│   └── api/
│       ├── __init__.py
│       └── main.py          # FastAPI Web API実装
├── tests/
│   ├── test_core/
│   │   ├── test_url_normalizers.py # URL正規化システムテスト
│   │   ├── test_youtube_client.py  # YouTube APIクライアントテスト
│   │   └── ...
│   ├── test_cli/
│   └── test_api/
├── docs/
├── config.example.yaml      # 設定ファイル例
├── pyproject.toml
└── README.md
```

## 完了条件

1. ✅ コアライブラリが指定されたURLからRSSフィードを正常に生成できる
2. ✅ 既存フィード検出・代理取得機能が正常に動作する
3. ✅ CLI版がコマンドライン引数と設定ファイルの両方に対応している
4. ✅ CLI版でWeb API URL生成機能が正常に動作する
5. ✅ Web API版（FastAPI）が正常に起動・動作する
6. ✅ Web APIサーバー起動コマンド（feedgen-serve）が動作する
7. ✅ 全テストがパスしている（91テスト）
8. ✅ Ruffによるコード品質チェックがパスしている
9. ✅ 基本的なドキュメントが整備されている

**🎉 全機能完成済み - 本格運用可能状態**