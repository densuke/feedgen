# feedgen 仕様書（EARS表記法）

## システム概要

URLの内容を分析してRSS Feedを生成するシステム。
コアライブラリ、CLI版、Web API版の3層構造で実装する。

## コアライブラリ（feedgen.core）

### Feed生成機能

**Event**: URLが指定されたとき
**Actor**: FeedGeneratorクラス
**Response**: 指定されたURLの内容を分析し、RSS形式のフィードを生成する
**System**: feedgen.core.FeedGenerator

#### 詳細動作

1. URLからWebページを取得
2. HTMLを解析してメタデータ（タイトル、説明、記事一覧等）を抽出
3. RSS 2.0形式のXMLを生成
4. 生成したRSSフィードを返却

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
```

## Web API版（将来実装）

### HTTP API機能

**Event**: GETリクエストでURLパラメータが指定されたとき
**Actor**: Web APIサーバー
**Response**: コアライブラリを使用してRSSフィードを生成し、XML形式でレスポンスする
**System**: feedgen.api.main

#### APIエンドポイント

```
GET /feed?url=<target_url>&max_items=<number>
```

#### レスポンス形式

- **成功時**: Content-Type: application/rss+xml
- **エラー時**: Content-Type: application/json

## 技術仕様

### 必要なライブラリ

- `requests`: HTTP通信
- `beautifulsoup4`: HTML解析
- `feedgenerator`: RSS生成
- `pydantic`: データバリデーション
- `click`: CLI構築
- `pyyaml`: 設定ファイル処理
- `pytest`: テスト実行
- `ruff`: コード品質チェック

### プロジェクト構造

```
feedgen/
├── feedgen/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── generator.py      # FeedGeneratorクラス
│   │   ├── parser.py         # HTML解析機能
│   │   ├── models.py         # データモデル
│   │   └── exceptions.py     # 例外クラス
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── main.py          # CLIメイン処理
│   │   └── config.py        # 設定管理
│   └── api/                 # 将来実装
│       ├── __init__.py
│       └── main.py
├── tests/
│   ├── test_core/
│   ├── test_cli/
│   └── test_api/
├── docs/
├── pyproject.toml
└── README.md
```

## 完了条件

1. コアライブラリが指定されたURLからRSSフィードを正常に生成できる
2. CLI版がコマンドライン引数と設定ファイルの両方に対応している
3. 全テストがパスしている
4. Ruffによるコード品質チェックがパスしている
5. 基本的なドキュメントが整備されている