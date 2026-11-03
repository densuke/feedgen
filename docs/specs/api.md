# Web API と CLI の仕様 (Rust 版)

作成日: 2026-11-03
状態: ドラフト (レビュー待ち)。承認までは足場・テスト・実装に着手しない。
親仕様: [pipeline.md](pipeline.md) (G-1〜G-11、8 章の申し送り)。コアは `feedgen-core` (`FeedGenerator`)。
移植元: Python 版 `feedgen/api/main.py`、`feedgen/cli/main.py`、`feedgen/cli/webapi.py`。

## 1. 目的と範囲

- **Web API** (`feedgen-server`): `GET /feed` が、URL を受け取り、RSS を返す。`GET /health`、`GET /` も持つ。axum で作る。
- **CLI** (`feedgen`): URL を受け取り、RSS を標準出力かファイルへ出す。`--generate-url` で Web API の URL を作る。

どちらも、コアの `FeedGenerator::generate` を呼ぶだけの薄い層にする。取得・検出・解析・SSRF 対策は、コアの責務。

対象外: Google News のデコード、翻訳、YouTube、Instagram (e2 の実測で利用 0 かごく少数。rust-reboot-spec.md、pipeline.md G-6)。FastAPI の自動ドキュメント (`/docs`、`/redoc`、`/openapi.json`)。

## 2. Python 版の挙動と、本番 (e2) の実測 (2026-11-03)

- エンドポイントは `/` (情報の JSON)、`/feed`、`/health` (`{"status": "healthy", "service": "feedgen API"}`)、FastAPI の `/docs` ほか。CORS は全オリジン・GET のみ・全ヘッダ。
- `/feed` のクエリ: `url` (必須)、`max_items` (1〜100、既定 20)、`use_feed`、`feed_first` (真偽値)、`user_agent`、`decode_google_news`、`google_news_interval` (1〜60)、`google_news_timeout` (5〜120)、`google_news_cache_ttl` (300〜604800)、`google_news_cache_type` (`memory` / `redis`)、`translate`、`translation_api_key`、`translation_target_lang`。範囲外は FastAPI が 422 を返す。
- 成功: 生成したフィードは `application/rss+xml; charset=utf-8`。代理取得は、`Content-Type` を `rss` / `atom` / それ以外で `application/rss+xml` / `application/atom+xml` / `application/xml` に直し、常に `charset=utf-8` を付ける。`feed_first` で検出したときは、`X-Existing-Feed-URL` / `-Title` / `-Type` を付ける。
- エラー本文は FastAPI 標準の `{"detail": …}` (文字列、または辞書)。`FeedGenerationError` と `ParseError` は 400、想定外は 500 (`Internal server error`、詳細はログのみ)。
- **ヘッダの値に日本語を含むと、Starlette が latin-1 で符号化できず 500 になる** (コードからの推論。`X-Existing-Feed-Title` に、`<link>` の `title` をそのまま入れるため)。
- 本番の呼び出し側 (868 件):
  - `decode_google_news` は 856 件すべて `false`、`google_news_*` は既定値 (`interval=1`、`timeout=10`、`cache_ttl=86400`、`cache_type=memory`)。
  - `user_agent` は 865 件すべて `feedgen-api/1.0`。
  - `max_items` は 20 が 572 件、5 が 293 件、1 が 1 件。`use_feed` は `false` が 572 件、`true` が 293 件。`feed_first` は `false` のみ。
  - `translate` 系は 0 件。
- 本番の応答は、499 (クライアントの中断) が約 38% (325 件)。応答が遅い取得先 (`use_feed` の `assets.wor.jp`、中央値 8.2 秒) に集中している。

## 3. Web API の要件 (EARS)

### A-1 エンドポイント

**Event**: HTTP リクエストを受けたとき
**Response**:

| メソッドとパス | 応答 |
|---|---|
| `GET /feed` | A-2〜A-4 |
| `GET /health` | `200`、`{"status": "healthy", "service": "feedgen API"}` |
| `GET /` | `200`、サービス名・バージョン・説明・`/feed` と `/health` の説明を持つ JSON |
| 上記以外のパスとメソッド | `404` / `405`。本文は `{"detail": "…"}` |

CORS は、全オリジン、`GET` のみ、全ヘッダを許可する (Python 版と同じ)。認証情報つきの CORS は、許可しない (全オリジンと認証情報の組み合わせは、仕様上、意味を持たない)。

### A-2 クエリパラメータ

| 名前 | 型・範囲 | 既定 | 違反したとき |
|---|---|---|---|
| `url` | 文字列。必須。2048 文字以内 | (なし) | なし → `422`。2048 文字超 → `400` |
| `max_items` | 整数 1〜100 | 20 | `422` |
| `use_feed` | 真偽値 | false | `422` |
| `feed_first` | 真偽値 | false | `422` |
| `user_agent` | 可視 ASCII (U+0020〜U+007E) のみ、1〜256 文字 | `feedgen-api/1.0` | `400` |

真偽値は、Python 版 (FastAPI / pydantic) と同じく、大文字小文字を区別せず `true` / `1` / `on` / `t` / `y` / `yes` を真、`false` / `0` / `off` / `f` / `n` / `no` を偽とする。ほかの値は `422`。

**受理して無視するもの** (本番の呼び出しが毎回付けている。値の検証はしない): `google_news_interval`、`google_news_timeout`、`google_news_cache_ttl`、`google_news_cache_type`、`google_news_cache_enabled`、`translation_api_key`、`translation_target_lang`。**未知のパラメータ**も無視する。

**非対応の機能を求められたとき**: `decode_google_news` が真、または `translate` が真なら、`400` で `この機能は未対応です (decode_google_news)` のように、機能名を含めて返す。黙って無視すると、呼び出し側は、機能が働いていると誤解する。(本番の呼び出しは、`decode_google_news` が常に `false`、`translate` は 0 件なので、影響しない。)

### A-3 成功の応答

**Response**: コアの `generate(url, options, now)` を呼ぶ。`options` は、`max_items`、`user_agent`、`use_feed`、`feed_first`。`now` は、リクエストを受けた時点の現在時刻 (UTC。API 層が 1 回だけ取得して渡す。G-4)。

- `Outcome::Generated`: `200`。`Content-Type` は `application/rss+xml; charset=utf-8`。本文は `feed.to_xml(now)`。`feed_first` で `detected` が空でないとき、先頭の候補を `X-Existing-Feed-URL` / `X-Existing-Feed-Title` / `X-Existing-Feed-Type` に入れる (A-7)。
- `Outcome::Proxied`: `200`。`Content-Type` は `Outcome` が持つ値のまま。本文はバイト列のまま。

### A-4 エラーの応答

**Response**: 本文は `{"detail": "…"}` (JSON。Python 版と同じ形)。

| 原因 | ステータス | `detail` |
|---|---|---|
| `url` なし、`max_items` の範囲外、真偽値でない値 | `422` | どのパラメータが、なぜ不正かを示す文字列 (Python 版の、辞書のリストとは形が違う) |
| `url` が長すぎる、`user_agent` が不正、非対応の機能 | `400` | 原因を示す文字列 |
| `FeedError::UnsafeUrl` (取得層の拒否、不正な URL) | `400` | コアのメッセージ (内部アドレスなどの詳細を含まない。ssrf.md S-9) |
| `FeedError::Http` (取得失敗、200 以外、上限超過) | `400` | コアのメッセージ |
| 全体のタイムアウト (A-5) | `504` | `処理に時間がかかりすぎました` |
| 同時実行の上限 (A-6) | `503` | `混雑しています。しばらくしてから再度お試しください` |
| 想定外のエラー、panic | `500` | `Internal server error` (詳細は返さず、ログに残す) |

**取得失敗を 400 とする理由**: Python 版と同じ。RSS リーダーは、200 以外をすべて失敗として扱う。上流の失敗を 502 とする方が意味は正しいが、既存の呼び出しへの影響はなく、違いを付ける利点が小さいので、Python 版を踏襲する。

### A-5 全体のタイムアウト

**Response**: `generate` 全体に、**60 秒**の締切を付ける。超えたら、`504`。

**Why**: `use_feed` の最悪の所要時間は、約 100 秒を超え得る (pipeline.md 8 章)。RSS リーダーの多くは、それより先に中断する (e2 の 499 が約 38%)。コアは、取得を 1 回にし、共通パスの確認を並列にしたので、通常の所要時間は、数秒で済む見込み。

### A-6 同時実行の上限

**Response**: 同時に処理する `/feed` を、**32 件**までにする。上限を超えるリクエストは、待たせず、直ちに `503` を返す。

**Why**: 公開のエンドポイントが、利用者の指定した URL を取得する。取得 1 回あたり最大 45 秒かかり得るので、上限がないと、少数のリクエストで、接続とメモリを使い切れる。32 は、e2 の実測 (9 日間で 868 件) に対して、十分に大きい。

**クライアントが切断したとき**: 処理 (`generate`) は、止めるか、締切 (A-5) まで続ける。**枠 (A-6) は、処理が終わるまで返さない**。切断で枠を返すと、遅い URL への接続と即切断を繰り返すだけで、上限なしに処理が積み上がる (e2 の 499 は約 38% で、通常の運用でも切断は起きる)。実装は、枠と締切を、処理を行うタスクの内側に置く。

### A-7 `X-Existing-Feed-*` ヘッダ

**Response**: 値は次のとおり作る。
- `X-Existing-Feed-URL`: 検出した URL (コアが `Url` から作るので、ASCII のみ)。
- `X-Existing-Feed-Type`: `RSS` / `Atom` / `JSON` / `XML`。
- `X-Existing-Feed-Title`: `<link>` の `title`。**制御文字を取り除き、200 文字に切り、ASCII の可視文字以外 (日本語など) を、UTF-8 のバイトごとに `%XX` で符号化する。`%` 自身も `%25` にする**。ヘッダの値の作成が失敗しても、panic せず、そのヘッダだけを付けない。

**Why**: ヘッダの値に、改行などの制御文字や、非 ASCII を、そのまま入れられない。Python 版は、日本語のタイトルで 500 になり得る (2 章)。`%` を符号化しないと、元から `%E3%81%82` を含むタイトルと、「あ」を符号化した結果が区別できない。受け手は、`%XX` を 1 回だけ復号すれば、元のタイトルを (制御文字と 200 文字を超える部分を除いて) 復元できる。

### A-8 サーバーの起動

**Response**:
- 待ち受けるホストとポートは、**コマンドライン引数 (`--host`、`--port`) > 環境変数 (`FEEDGEN_HOST`、`FEEDGEN_PORT`) > 既定 (`127.0.0.1`、`8000`)** の順で決める。直接公開するときだけ `0.0.0.0` にする (Caddy の背後では `127.0.0.1`)。
- ホストは IP アドレスのみ (`localhost` などのホスト名は受け付けない)。**空文字の環境変数は、未設定として扱う** (systemd の `Environment=FEEDGEN_HOST=` を踏まないため)。コマンドライン引数の空文字は、エラー。
- 不正なホストやポートは、起動時にエラーで終了する。
- `SIGTERM` の登録に失敗したときは、そのことをログに出す。
- `SIGTERM` と Ctrl-C で、処理中のリクエストの完了を待ってから (締切 30 秒) 終了する (systemd の再起動で、応答を途中で切らない)。
- `--reload` は持たない (開発用で、Rust では意味がない)。
- 起動時に、待ち受けのアドレスをログに出す。リクエストごとのアクセスログは出さない (Caddy が記録する)。エラーは、原因をログに残す。

## 4. CLI の要件 (EARS)

### C-1 コマンド

**Event**: `feedgen <URL> [オプション]` を実行したとき
**Response**: `FeedGenerator::generate` を呼び、結果を出力する。現在時刻は、CLI が 1 回だけ取得して渡す。

| オプション | 意味 |
|---|---|
| `-c`, `--config <PATH>` | 設定ファイル (C-2) |
| `-o`, `--output <PATH>` | 出力先のファイル (なければ標準出力) |
| `--max-items <N>` | 最大記事数 (1〜100。範囲外はエラー) |
| `--user-agent <STR>` | `User-Agent` (A-2 と同じ検証) |
| `--use-feed` | 既存フィードがあれば代理取得 |
| `--feed-first` | 既存フィードの検出結果を stderr に表示し、HTML 解析も続ける |
| `--generate-url` | Web API の URL を生成して出力 (C-4) |
| `--api-host <HOST>` | `--generate-url` の API のホスト |

Google News と翻訳のオプション (`--decode-google-news`、`--google-news-*`、`--translate`、`--translation-*`) は持たない。指定すると、`clap` が、未知のオプションとしてエラーにする。

**出力**: `Generated` は、`feed.to_xml(now)`。`Proxied` は、本文のバイト列のまま。出力先がファイルのときは、ファイルに書き、`出力しました: <PATH>` を stderr に出す。

**`--feed-first` の表示**: `detected` が空でなければ、先頭の候補を、stderr に `既存フィード: <種類> <URL> (<タイトル>)` の形で出す (Python 版は、API のヘッダに相当する情報を、CLI では出していなかった。stderr に出すことで、XML の出力を汚さない)。**タイトルは取得先の文字列なので、制御文字 (ANSI のエスケープ、改行など) を取り除いてから出す** (端末の表示を書き換えられないように)。

### C-2 設定ファイル

**Response**: `--config` で指定されたファイル、なければ、カレントディレクトリの `config.yaml` (なければ設定なしとして続行)。読む項目は `max_items`、`user_agent`、`api_base_url` のみ。優先順位は、コマンドライン引数 > 設定ファイル > 既定。

- 指定された設定ファイルが存在しない、または YAML として読めないときは、エラー。
- **未知のキー**は、警告 (stderr) を出して無視する (`instagram.max_post` のような綴り違いに気づけるように)。Python 版の他のキー (`youtube_api_key`、`google_news`、`instagram`、`translation`) は、対象外の機能なので、警告の対象になる。

**Python 版との違い**: Python 版は、カレントディレクトリから上位に向かって `config.yaml` を探す。Rust 版は、カレントディレクトリだけにする (KISS。上位を探す必要がある使い方は、確認できていない)。

### C-3 終了コード

**Response**: 成功は 0。失敗 (取得・生成のエラー、引数や設定の誤り、出力の書き込みの失敗) は 1 で、メッセージを stderr に出す (stdout には出さない)。

### C-4 `--generate-url`

**Event**: `--generate-url` が指定されたとき
**Response**: 取得せずに、Web API の URL を生成して出力する (`-o` があればファイルへ)。`{api_host を正規化したもの}/feed?{クエリ}` の形。

- API のホストは、`--api-host`、なければ設定ファイルの `api_base_url`。どちらもなければエラー。
- 正規化: スキームがなければ `https://` を付け、末尾の `/` を除く。スキームとホストがなければエラー (`検証`)。
- クエリは、`url` を先頭に、指定されたものだけを、`max_items`、`use_feed`、`feed_first`、`user_agent` の順に並べる (値は URL エンコード。真偽値は `true` / `false`)。Python 版が付けていた `decode_google_news` と `google_news_*` は、付けない。

## 5. 実装方針 (KISS)

- 構成は、`crates/feedgen-server` (axum。ライブラリとバイナリ) と `crates/feedgen-cli` (clap。バイナリ `feedgen`)。ワークスペースのメンバーに足す。
- API 層は、`generate` を trait (`FeedService`) 越しに呼ぶ。本番は `FeedGenerator`、テストは通信しない偽物を差し込む。コアの `with_fetcher` はテスト専用で、ほかのクレートからは見えない (本番に「ループバックを許可する」口を作らない。ssrf.md S-10)。コアの実際の取得は、コア側のテストが確かめている。
- タイムアウトと同時実行の上限は、構成値として持つ (本番は 60 秒と 32 件)。テストで短い値を差し込めるようにする。
- クエリの解析は、純粋な関数 (文字列の組 → 検証済みのリクエスト、またはエラー) にし、単体で表のテストをする。
- YAML は、保守されているクレートを選ぶ (`serde_yaml` は保守が終了している。実装時に現状を確認する)。

## 6. テスト方針

- **クエリの解析** (表のテスト。軽い): 必須、範囲、真偽値の別名と大文字小文字、`user_agent` の検証 (長さ、制御文字、非 ASCII、境界)、`url` の長さ、受理して無視するもの、未知のパラメータ、非対応の機能。
- **Router** (偽の `FeedService`。`tower::ServiceExt::oneshot`。通信なし): `/`、`/health`、404 / 405、CORS (オリジン、プリフライト、`GET` のみ)、成功の 2 種類 (ヘッダ、本文、`Content-Type`)、エラーの対応表 (A-4)、`X-Existing-Feed-*` (日本語のタイトル、制御文字、長いタイトル、`feed_first` で候補なし)、`use_feed` と `feed_first` の値が `generate` に渡ること、`user_agent` の既定値。
- **タイムアウトと上限** (短い構成値と、止まる偽物): 締切で `504`、上限で `503` (待たずに返る)、完了後に枠が戻ること。
- **サーバーの起動** (引数と環境変数の優先順位は、純粋な関数として表のテスト。実際の起動は、`main` の薄い部分で、テストしない。理由は、README か設計文書に書く)。
- **CLI**: 引数の解析、設定ファイル (優先順位、未知のキー、存在しないファイル)、`--generate-url` (正規化と順序のテーブル)、出力 (標準出力、ファイル、`Proxied` のバイト列、`--feed-first` の stderr)、終了コード。通信を伴う部分は、`generate` を差し替えて確かめる。
- **Python 版との比較** (golden): `--generate-url` の出力は、Python 版の `URLGenerator` と、同じ入力で比べる (`google_news` 系を除く)。

## 7. Python 版との差

| 項目 | Python 版 | Rust 版 | 状態 |
|------|-----------|---------|------|
| エラー本文 | `{"detail": …}` | 同じ | 維持 (spec.md の `{"error": …}` は実態と違った) |
| 422 の本文 | 辞書のリスト | 文字列 | 簡略化 |
| `user_agent` の検証 | なし | 可視 ASCII、256 文字 | 追加 (400) |
| `url` の長さ | 無制限 | 2048 文字 | 追加 (400) |
| 非対応の機能 (`decode_google_news=true`、`translate=true`) | 動く | 400 | 明示的に拒否 |
| `google_news_*` の範囲検証 | あり (422) | なし (受理して無視) | 簡略化 |
| 代理取得の `Content-Type` | 常に `charset=utf-8` を付ける | 元の `charset` (知っているラベルのみ) | pipeline.md D-6 |
| `X-Existing-Feed-Title` | そのまま (日本語で 500 になり得る) | 符号化 (`%` も)、長さ制限 | 直す |
| 重複したクエリのキー (`?max_items=1&max_items=2`) | 最後の値 | 先頭の値 | 差 (本番の呼び出しは重複しない) |
| 不正な `%` エンコードのクエリ | FastAPI が解釈 | `400` (`クエリを解釈できません`) | 簡略化 |
| `HEAD /feed` | `405` | `GET` と同じ処理 (axum の既定) | 差 (読み取りのみで、枠も使う) |
| タイムアウト | なし | 60 秒 (504) | 追加 |
| 同時実行の上限 | なし | 32 件 (503) | 追加 |
| `/docs`、`/redoc`、`/openapi.json` | あり | なし | 対象外 (Caddy が自分の接続元に限定していた) |
| Instagram のエラー (401、429) | あり | なし | 対象外 |
| CLI の設定ファイルの探索 | 上位ディレクトリまで | カレントのみ | 簡略化 |
| CLI の `--feed-first` の通知 | なし (API のヘッダのみ) | stderr に表示 | 追加 |
| `--reload` | あり | なし | 対象外 |

## 8. 未決事項 (推奨つき)

- **D-A1** エラー本文は、Python 版と同じ `{"detail": …}` にする。推奨: この方針。元の `spec.md` は `{"error": …}` と書いていたが、実際の Python 版の応答は `detail` で、既存の呼び出し側は、こちらを前提にしている可能性がある。
- **D-A2** 全体のタイムアウトは 60 秒で、`504` を返す。推奨: この方針。RSS リーダーの多くは、これより先に中断する。
- **D-A3** 同時実行は 32 件までで、超えたら直ちに `503` を返す。推奨: この方針。公開エンドポイントの増幅を防ぐ。32 件は、実測に対して十分に大きい。
- **D-A4** `decode_google_news=true` と `translate=true` は、黙って無視せず、`400` で拒否する。推奨: この方針。本番の呼び出しは影響を受けない。
- **D-A5** CLI の `--generate-url` は移植し、Google News と翻訳のオプションは移植しない。推奨: この方針。`--generate-url` は小さく、Python 版の README に載っている機能。e2 の呼び出しがこれで作られているかは、確認できていない。
- **D-A6** `X-Existing-Feed-Title` は、非 ASCII を `%XX` で符号化する。推奨: この方針。代わりに、日本語などの非 ASCII を落として ASCII の部分だけを残す案もある (読みにくくなる)。
- **D-A7** 422 の本文は、Python 版 (FastAPI の辞書のリスト) と違い、文字列にする。推奨: この方針。422 の本文を解析している呼び出し側は、確認できていない。
