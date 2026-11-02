# feedgen Rust 版リブート仕様 (EARS)

作成日: 2026-11-03
状態: ドラフト。Q1・Q4 は決定済み、Q2・Q3 は e2 の調査結果を反映済み (6章・7章)。

## 1. 背景と現状

- Python 版 (main 21814f8) は core / cli / api で約 3,900 行。
- 旧 Rust 版は worktree `feedgen-rs` のブランチ `feature/rust-port` にある (最終コミット 2026-06-20)。
  - フェーズ0〜6まで実装済み。`--features full` で 98 テストが全通過する。
  - 構成は feedgen-core / feedgen-cli / feedgen-server の 3 クレート。
- Python の SSRF 対策 (リモートのブランチ名は `fix/ssrf`、2026-11-02、3 コミット) は 2026-11-03 に main へ `--no-ff` でマージ済み (4434803、pytest 353 件全通過)。push は未実施。旧 Rust 版には SSRF 対策がない。
- このドキュメントは「やりなおし」の対象範囲と、移植の判断基準を定める。

## 2. Python 版の「プラグイン」の実体

サイト別の HTML 抽出プラグインは存在しない。次の 3 種類のみ。

| 種別 | 内容 | 必要な能力 |
|------|------|-----------|
| (a) URL 正規化 4 種 | GoogleNews / YouTube / Instagram / Default | 文字列規則のみ |
| (b) プロバイダ 3 種 | YouTube API、Instagram (軽量/フル)、Google News デコード。`FeedGenerator` の if/elif に直書き | HTTP、JSON、秘密情報、認証 |
| (c) 後処理 1 種 | Gemini 翻訳 | HTTP、JSON、API キー、キャッシュ |

## 3. 要件 (EARS)

### 3.1 基盤

**R-1** URL が指定されたとき、FeedGenerator は既存フィード検出、HTML 解析 3 戦略 (見出し / カード / コンテンツブロック)、タイトル重複排除を経て RSS 2.0 を返す。(Python 版と同一挙動)

**R-2** 外部取得が必要なとき、システムは `HttpClient` trait 経由でのみ通信する。テストは `MockHttpClient` を注入し、実ネットワークに依存しない。

**R-3** 設定は CLI 引数 > 環境変数 > YAML > 既定値の優先順位で解決する。

### 3.2 セキュリティ (必須)

**R-10** 取得先 URL が指定されたとき、システムは接続前に次を検査し、違反なら取得せずエラーにする。
- スキームが http / https 以外
- 解決先アドレスがループバック、プライベート、リンクローカル、メタデータ用アドレス

**R-11** リダイレクトが発生したとき、システムはリダイレクト先ごとに R-10 を再検査する。

**R-12** 応答を受信するとき、システムは応答サイズの上限と締切時間を適用する。

**R-13** エラーを API 応答に含めるとき、システムは API キー等の秘匿値を伏せ、内部エラーの詳細は返さずログにのみ残す。

**R-14** API キーは環境変数または設定ファイルから受け取る。クエリ文字列では受け取らない。(Python 版の `translation_api_key` クエリは移植しない)

SSRF ガードの実装はホスト側の取得関数 1 か所に集約する。Rhai を導入する場合も、スクリプトから呼べる HTTP 関数はこの経路のみとする。

### 3.3 プロバイダと後処理

**R-20** URL が指定されたとき、システムは登録済み `Provider` を順に評価し、最初に `matches(url)` が真のものに処理を委ねる。該当がなければ汎用 HTML 経路に進む。

**R-21** Provider が失敗したとき、システムは HTML 解析にフォールバックする。ただし Instagram の認証エラー (401) とレート制限 (429) は呼び出し元に伝える。(旧 Rust 版踏襲)

**R-22** フィード生成後、翻訳が有効なとき、`Postprocessor` がタイトルと説明を翻訳する。失敗時は原文を残す。

トレイト案 (確定ではない):

```rust
trait Provider { fn matches(&self, url: &Url) -> bool; fn fetch(&self, ctx: &Ctx) -> Result<RssFeed>; }
trait Postprocessor { fn apply(&self, ctx: &Ctx, feed: RssFeed) -> RssFeed; }
```

### 3.4 Rhai の位置づけ

**R-30** Rhai は「宣言的な層」(URL 書き換え規則、CSS セレクタ指定) に限って採用を検討する。YouTube / Instagram / Gemini は静的な Rust の Provider とする。

**R-31** Rhai を採用する場合、エンジンは `Engine::new_raw()` で作り、公開するホスト関数を最小にする。次の上限を設定する: 演算回数、呼び出し深さ、文字列/配列/マップサイズ、式の深さ、モジュール数。モジュールリゾルバは既定の `FileModuleResolver` から差し替え、ファイル読み込みを塞ぐ。

**R-32** Rhai の採用可否は、未決事項 Q3 (ユーザー自作ルールの要否) の回答で決める。

### 3.5 パリティと検証

**R-40** HTML パーサの出力について、実 HTML フィクスチャを保存し、Python 版の出力を期待値とする golden テストで Rust 版と照合する。BeautifulSoup (`html.parser`) と scraper (html5ever) の差が出やすい箇所は `get_text()` の空白処理、`find_next`、`limit=`。

**R-41** Web API は Python 版と同じクエリパラメータを受け付ける (R-14 を除く)。範囲外の `max_items` は Python 版同様に 422 で拒否する。
- 既存の呼び出し側が `decode_google_news` と `google_news_*` を毎回付けて送っている (e2 の実測、7章)。Google News デコードを廃止しても、これらのパラメータは**受理して無視**し、拒否しない。
- 上記以外の未知のパラメータは、無視するか拒否するかを仕様として明示し、黙って捨てない。

**R-42** YAML 設定は Python 版のキー (`youtube_api_key` / `google_news` / `instagram` / `translation` 等) を読む。ただし秘匿値は環境変数を優先する。

### 3.6 廃止・非対応

| 機能 | 方針 | 理由 |
|------|------|------|
| Google News デコード | 廃止を推奨 | Rust に等価ライブラリがなく、Google 側の Bot 検出で実用上ほぼ動かない (spec.md 自身も認めている) |
| Instagram フル版 | 非対応を推奨 | instaloader 依存とログインセッション管理が重い |
| Gemini モデル名 `gemini-1.5-flash` | 移植しない | 両実装でハードコード。現行のモデル名を確認して設定可能にする |

## 4. 旧 feedgen-rs の流用方針

新ブランチ `feature/rust-reboot` で再設計する (Q1 の決定)。旧ブランチ `feature/rust-port` はマージせず、必要な部品だけを手で移す。

- **そのまま流用**: `http.rs` (SSRF 追加が前提)、`models.rs`、`normalize.rs`、`feed_detector.rs`、`url_generator.rs`
- **参考にして書き直す**: `parser.rs` (R-40 の検証後)、`youtube.rs`、`translate.rs`、`translation_cache.rs`、`instagram.rs`
- **作り直す**: `generator.rs` (R-20 の Provider 構成へ)、`feedgen-server/lib.rs` (R-10〜R-14、R-41 を満たす形へ)

## 5. 実装順の案

1. (完了) Python の SSRF 対策を main に取り込み、パリティ基準とする (Q4)
2. `HttpClient` に SSRF ガードを実装し、テストを書く (R-10〜R-12)
3. golden フィクスチャを作り、パーサを検証する (R-40)
4. Provider / Postprocessor 構成へ generator を組み替える (R-20〜R-22)
5. API と YAML 設定のパリティを埋める (R-41、R-42)
6. 必要なら Rhai の宣言的な層を追加する (R-30〜R-32)

## 6. 決定事項と未決事項

- **Q1 (決定)** 新ブランチで再設計する。`feature/rust-reboot` を main (4434803) から作成済み。
- **Q2 (調査済み・最終判断は保留)** 本番はほぼ汎用 HTML 解析で、YouTube が少量。Google News デコード・Instagram・翻訳は直近 9 日間の利用がゼロ。移植の優先度は 8 章に従い、廃止・非対応の確定はユーザー判断とする。
- **Q3 (保留)** 現時点で Rhai が必要だという根拠は出ていない。per-site ルールの要否は、golden テスト (R-40) で 3 ブログと市サイトの出力品質を確認してから決める。
- **Q4 (決定)** 安全第一で SSRF 対策を先に main へマージし、Rust 版にも同等の対策を入れる。Python 側は完了、Rust 側は 5 章の手順 2。

## 7. 本番 (e2) の実態

調査日 2026-11-03、読み取りのみ。調査期間は Caddy のジャーナルが残っている 2026-10-26〜11-03。秘密値は読んでいない。

**稼働形態**
- `feedgen.service` (systemd)。uvicorn が `0.0.0.0:8000` で待ち受け、Caddy が `feedgen.fuga.jp` を中継する。`/docs` 系は自分の接続元に限定済み、`/feed` は公開。
- e2 の main は origin/main より 3 コミット進み (SSRF 対策)、17 コミット遅れている (翻訳機能などが未デプロイ)。
- `uvicorn` が全インターフェースで待ち受けているため、ファイアウォール次第で Caddy を迂回して `:8000` に直接届く可能性がある。Rust 版のデフォルトは `127.0.0.1` を維持する (旧 Rust 版踏襲)。

**`/feed` の利用 (860 件)**
- 対象は assets.wor.jp (291 件、`use_feed=true`)、mfujin.blog.jp (283 件)、kabumatome.doorblog.jp (263 件) の 3 ブログが約 840 件。残りは www.youtube.com が 9 件、kotsu.city.kobe.lg.jp が 8 件。
- Google News、Instagram、翻訳の利用はゼロ。
- 応答は 200 が 529 件、499 (クライアント中断) が 325 件 (約 38%)、400 が 6 件。200 時の所要時間の中央値は assets.wor.jp が 8.2 秒、2 つのブログが約 2.5〜2.8 秒。遅い応答が 499 の一因と考えられる。Rust 版では所要時間の短縮が見込める。
- 呼び出し側は `max_items` / `use_feed` / `feed_first` / `user_agent` / `decode_google_news` / `google_news_*` を毎回付ける (R-41)。

**SSRF 探査の実例**
- 169.254.169.254、localhost:2019 (Caddy 管理 API)、127.0.0.1:9998、[::1]:9997、`127.0.0.1\@8.8.8.8` (URL 解析差を狙ったもの)、空の url の 6 件が来ており、すべて 400 で拒否された。R-10〜R-13 は実害のある要件である。テストケースにこの 6 種を含める。

**設定**
- `config.yaml` は YouTube API キー設定済み、Instagram フル版が有効。ただし Instagram の利用はゼロ。
- `instagram.max_post` は `max_posts` の綴り違いで、Python 版で無視されている可能性がある。Rust 版では未知のキーを検出して警告する。

## 8. 未確認事項

- Instagram 軽量版のキャッシュ (TTL 5 分) とリトライが旧 Rust 版にあるか。
- Rhai に標準で I/O が組み込まれていないことの公式文言 (一般知識として扱っている)。
