# feedgen

URLの内容を分析して、RSS 2.0 のフィードを生成するツール。Rust 製の Web API (`feedgen-server`) とコマンドライン (`feedgen`) がある。

## 機能

- 既存の RSS / Atom / JSON Feed の検出と代理取得
- 多戦略の HTML 解析による RSS 2.0 の生成
- URL 自体が RSS / RDF / Atom のときは、そのまま返す
- 文字コードの判定 (BOM、`Content-Type`、`<meta>`)
- SSRF 対策つきの取得 (下の「安全性」)
- 設定ファイル (YAML) によるコマンドラインの既定値
- YouTube の検索結果の URL (`https://www.youtube.com/results?search_query=…`) を、YouTube Data API で動画のフィードにする。API キーは環境変数 `YOUTUBE_API_KEY` (サーバーと CLI の起動時に読む)。キーがない、または API が失敗したときは、空のフィードではなくエラー (API は 400)。チャンネルと再生リストは対象外。仕様は [docs/specs/youtube.md](docs/specs/youtube.md)

**対象外**: Instagram、Google News のデコード、翻訳、redis キャッシュ。以前の Python 版にあった機能で、利用実績がなく、Rust 版には移植していない。Python 版はフェードアウト中で、保守しない。

## インストール

リリースのバイナリ (Linux x86_64, 静的リンク) を使うか、ソースからビルドする。

```bash
# ソースからビルド (Rust 1.88 以上。let チェーンを使うため)
cargo build --release
# 成果物: target/release/feedgen-server と target/release/feedgen
```

リリースは [GitHub の Releases](https://github.com/densuke/feedgen/releases) に、`feedgen-x86_64-unknown-linux-musl-<版>.tar.gz` (と `.sha256`) として置かれる。中身は `feedgen` と `feedgen-server` の 2 つ。

## Web API

```bash
# 起動 (既定は 127.0.0.1:8000)
feedgen-server
feedgen-server --host 0.0.0.0 --port 8080

# 環境変数でも指定できる (引数が優先)
FEEDGEN_HOST=127.0.0.1 FEEDGEN_PORT=8000 feedgen-server
```

公開するときは、リバースプロキシ (Caddy など) の背後に置く。`0.0.0.0` にするのは、直接公開するときだけ。`SIGTERM` と Ctrl-C で、処理中のリクエストの完了を待って (最大 30 秒) 終了する。

### エンドポイント

| パス | 内容 |
|---|---|
| `GET /feed` | URL からフィードを返す |
| `GET /health` | 死活確認。`{"status":"healthy","service":"feedgen API"}` |
| `GET /` | サービス情報 |

CORS は、全オリジン、`GET` のみ許可する。

### `/feed` のパラメータ

| 名前 | 内容 | 既定 |
|---|---|---|
| `url` | 対象の URL (必須。2048 文字以内) | なし |
| `max_items` | 最大記事数 (1〜100) | 20 |
| `use_feed` | 既存のフィードがあれば、代理取得する (真偽値) | false |
| `feed_first` | 既存フィードの検出結果をヘッダに付け、HTML の解析も続ける (真偽値) | false |
| `user_agent` | 取得時の User-Agent (可視 ASCII、1〜256 文字) | `feedgen-api/1.0` |

真偽値は `true` / `1` / `on` / `t` / `y` / `yes` と、`false` / `0` / `off` / `f` / `n` / `no` (大文字小文字は問わない)。

```bash
curl "http://127.0.0.1:8000/feed?url=https://example.com/&max_items=5"
curl "http://127.0.0.1:8000/feed?url=https://example.com/&use_feed=true"
```

### 応答

- 生成したフィード: `application/rss+xml; charset=utf-8`
- 代理取得: 元のフィードの本文のまま。`Content-Type` は `application/rss+xml` か `application/atom+xml` (元の `charset` があれば引き継ぐ)
- `feed_first` で検出したとき: `X-Existing-Feed-URL`、`X-Existing-Feed-Title` (日本語などは `%XX` で符号化)、`X-Existing-Feed-Type`
- エラー本文は `{"detail": "…"}`

| 状況 | ステータス |
|---|---|
| `url` なし、`max_items` の範囲外、真偽値でない値 | 422 |
| `url` が長すぎる、`user_agent` が不正、非対応の機能 (`decode_google_news=true`、`translate=true`) | 400 |
| 取得できない URL (内部アドレスなど)、取得の失敗 | 400 |
| 処理に 60 秒以上かかった | 504 |
| 同時に処理している `/feed` が 32 件を超えた | 503 |
| 想定外のエラー | 500 (詳細は返さない) |

`google_news_*` や `translation_*` など、Python 版のパラメータは、受け付けて無視する。

## コマンドライン

```bash
feedgen https://example.com/                      # 標準出力へ
feedgen --use-feed https://example.com/           # 既存フィードがあれば代理取得
feedgen --feed-first https://example.com/         # 検出結果を標準エラーに出す
feedgen -o feed.xml --max-items 10 https://example.com/
feedgen --config config.yaml https://example.com/
```

| オプション | 内容 |
|---|---|
| `-c`, `--config <PATH>` | 設定ファイル (なければ、カレントの `config.yaml`) |
| `-o`, `--output <PATH>` | 出力先のファイル (なければ標準出力) |
| `--max-items <N>` | 最大記事数 (1〜100) |
| `--user-agent <STR>` | User-Agent |
| `--use-feed` / `--feed-first` | 上の API と同じ |
| `--generate-url` | 取得せず、Web API の URL を生成して出力 |
| `--api-host <HOST>` | `--generate-url` の API のホスト |

失敗したときは、終了コード 1 で、メッセージを標準エラーに出す。

### Web API の URL の生成

```bash
feedgen --generate-url --api-host feedgen.example.com --max-items 5 --use-feed https://blog.example.com/
# https://feedgen.example.com/feed?url=https%3A%2F%2Fblog.example.com%2F&max_items=5&use_feed=true
```

### 設定ファイル

読む項目は 3 つだけ。優先順位は、コマンドライン引数、設定ファイル、既定の順。未知のキーは、警告を出して無視する。

```yaml
max_items: 20
user_agent: "feedgen/1.0"
api_base_url: https://feedgen.example.com
```

## 安全性

公開するサービスが、利用者の指定した URL を取得するので、取得の層で SSRF を防ぐ。

- `http` と `https` のみ。ポートは 80 と 443 のみ
- DNS を 1 回だけ解決して、そのアドレスに接続する。非公開のアドレス (ループバック、プライベート、リンクローカル、メタデータなど) は拒否する
- リダイレクトは自分で辿り、移動先ごとに同じ検査をする
- 本文は 2 MiB まで。全体の締切は 45 秒
- 取得失敗のエラーに、内部のアドレスなどを含めない

詳細は [docs/specs/ssrf.md](docs/specs/ssrf.md)。

## 配備と自動更新

e2 での配備、更新スクリプト (検証、置き換え、起動後の `/health` が通らなければ自動でロールバック)、systemd のタイマーは [deploy/README.md](deploy/README.md)。仕様は [docs/specs/release.md](docs/specs/release.md)。

main への push で、GitHub Actions がビルドしてリリースする。Dependabot が、毎週月曜に、依存 (cargo) と Actions の更新を提案し、テストが通れば、自動でマージして、新しい版をリリースする。

## 開発

仕様 ([docs/specs/](docs/specs/)) を先に書き、テストを先に書いてから、実装する。

```bash
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
bash deploy/tests/test_deploy.sh   # 配備スクリプトのテスト
```

構成:

| クレート・ディレクトリ | 内容 |
|---|---|
| `crates/feedgen-core` | 取得、文字コード、検出、解析、パイプライン |
| `crates/feedgen-server` | Web API (axum) |
| `crates/feedgen-cli` | コマンドライン |
| `deploy/` | e2 の更新スクリプトと systemd |
| `docs/specs/` | 仕様 (ssrf、models、parser、pipeline、detector、api、release) |
| `tools/gen_golden.py` | Python 版の出力を、比較用の期待値にする道具 (解析のテスト用) |

## ライセンス

MIT
