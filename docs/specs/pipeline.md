# フィード生成パイプライン仕様 (Rust 版)

作成日: 2026-11-03
状態: ドラフト (レビュー待ち)。承認までは足場・テスト・実装に着手しない。
親仕様: [rust-reboot-spec.md](../rust-reboot-spec.md)。取得層は [ssrf.md](ssrf.md) (実装済み)。

## 1. 目的と範囲

URL を受け取り、RSS を返す一連の流れ (オーケストレーション) を定める。
個別の部品は別の仕様にする。この仕様は部品の境界と、つなぎ方、作る順序を決める。

| 部品 | 仕様 | 状態 |
|------|------|------|
| 取得層 (SSRF 対策) | ssrf.md | 実装済み |
| モデルと RSS 2.0 出力 | models.md (未作成) | 次 |
| HTML パーサ (3 戦略 + 重複排除) | parser.md (未作成) | その次 |
| 既存フィード検出 | detector.md (未作成) | |
| パイプライン (この仕様) | pipeline.md | ドラフト |
| Web API / CLI | api.md (未作成) | 最後 |

## 2. 現行 Python 版の流れ (移植元)

- `FeedGenerator.generate_feed(url, config)` (core): 設定の検証 → YouTube / Instagram の分岐 → HTML 解析。
- `use_feed` / `feed_first` の処理は **core ではなく API 層と CLI に重複して**書かれている。
  - 検出に失敗しても、HTML 解析に続行する (握りつぶす)。
  - `use_feed` が真で既存フィードが見つかれば、最初の 1 件を取得してそのまま返す (代理取得)。`use_feed` と `feed_first` が両方真なら `use_feed` が優先。
  - `feed_first` のみなら、HTML 解析を続行し、検出した情報を `X-Existing-Feed-*` ヘッダに付ける。
  - 代理取得の `Content-Type` は、`rss` を含めば `application/rss+xml`、`atom` を含めば `application/atom+xml`、それ以外は `application/xml` (いずれも `charset=utf-8`)。
- HTML パーサは、記事ごとに `pub_date = 現在時刻`、`guid = {base_url}#heading-{i}` などを入れる。出力が実行ごとに変わる。

## 3. 要件 (EARS)

### G-1 入口

**Event**: URL とオプションが渡されたとき
**Actor**: パイプライン (`generate`)
**Response**: 次の順で処理し、結果を `Outcome` で返す。`Outcome` は「生成したフィード (検出情報つき)」と「代理取得した本文と Content-Type」の 2 種類。
**System**: `feedgen-core::generator`

オプションは `max_items` (既定 20)、`user_agent`、`use_feed`、`feed_first`。範囲 (`max_items` は 1〜100) の検証は API 層で行い、core は検証済みの値を受け取る。

### G-2 処理の順序

1. `use_feed` または `feed_first` が真なら、既存フィードを検出する (detector.md)。
2. `use_feed` が真で、検出できたら、最初の 1 件を取得して `Proxied` で返す。
3. 検出または取得に失敗したときは、エラーを返さず、HTML 解析に進む (Python 版を踏襲)。
4. HTML を取得し、メタデータと記事一覧を抽出して、`Generated` で返す。`feed_first` が真なら、検出した情報を `detected` に入れる。

### G-3 取得はすべて取得層を通す

**Event**: 外部へ通信するとき
**Response**: 検出の `HEAD`、共通パスの確認、代理取得するフィード、HTML の取得を含め、すべて `SafeFetcher` を使う。直接 `reqwest` を呼ばない。

**Why**: HTML の `<link>` から見つかるフィード URL は、取得先サイトが書き換えられる値で、攻撃者が内部アドレスを指せる。代理取得の対象 URL も取得層で検査する。

### G-4 時刻は引数で渡す

**Event**: 記事の `pub_date` や `last_build_date` を決めるとき
**Response**: 現在時刻は呼び出し側 (パイプラインの入口) が 1 回だけ取得して渡す。パーサなどの部品は時刻を自分で取らない。

**Why**: Python 版の出力は実行ごとに変わる。時刻を固定できなければ、golden テストが成立しない。

### G-5 エラー

**Event**: 生成に失敗したとき
**Response**: `FeedError` で返す。HTTP ステータスへの対応づけは API 層 (api.md) の責務とする。
- 取得層の拒否 (`UnsafeUrl`) と取得失敗 (`Http`): 利用者の入力に起因するので 400 の系統。
- 内部の想定外: 500 の系統。詳細は返さずログに残す (ssrf.md S-9 と同じ方針)。

### G-6 プロバイダと後処理 (YAGNI)

e2 の実測 (860 件) で、専用処理が使われたのは YouTube 検索の 9 件のみ。Google News、Instagram、翻訳は 0 件。

**Response**:
- 現時点では `Provider` / `Postprocessor` の trait を作らない。実装が 0 個の抽象は持たない。
- YouTube を実装する時点で、`generate` の前段に「YouTube 検索 URL かつ API キーがある」場合の分岐を 1 つ足す。2 つ目のプロバイダが必要になった時点で、trait への抽出を検討する。
- Google News のデコード、Instagram、翻訳は対象外とする。要望が出たら別仕様にする。

## 4. 作る順序

各段階を「仕様 → テスト (RED) → 実装 (GREEN) → 独立レビュー」で進める。

1. **models.md**: `RssFeed` / `RssItem` と、RSS 2.0 の XML 出力。
   - 検証: Python (`feedgenerator.Rss201rev2Feed`) が出す XML と比べる。どこまで同一にするか (要素の順序、`guid` の `isPermaLink`、名前空間、`lastBuildDate`) を仕様に書く。
2. **parser.md**: HTML パーサ。golden テストで BeautifulSoup と scraper の差を測る。
3. **detector.md**: 既存フィード検出。
4. **パイプライン**: 上記をつなぐ (G-1〜G-5)。
5. **api.md**: axum の API と CLI。

## 5. golden テストの方法 (parser の前提)

1. 実在サイトの HTML を保存する。対象は e2 の主な 3 ブログと市のサイトの 4 件。サイズが大きい場合は、記事一覧の周辺だけに切り詰める。
2. Python 版 (main) で、時刻を固定して同じ HTML を解析し、期待値 (記事の一覧) を保存する。
3. Rust 版の出力が、期待値と一致することを確認する。
4. 差が出た箇所は、(a) Rust 側を合わせる、(b) Python 側の挙動が不具合なら、差を仕様に明記して Rust 側は正しい方にする、のどちらかを選び、記録する。

**注意**: 実サイトの HTML の取得は、外部への通信とファイルのダウンロードにあたる。実行前に、対象 URL とファイル名をお見せして、許可をいただく。

## 6. 未決事項

2026-11-03 に D1〜D4 を、推奨どおり決定した。

- **D1 (決定)** `Provider` trait を今は作らない (G-6)。
- **D2 (決定)** `max_items` の検証は API 層に置き、core は検証済みの値を受け取る (G-1)。
- **D3 (決定。実行時に再確認)** golden テストに使う実サイトの HTML を取得してよい。対象は 4 サイト。実際に取得する直前に、取得先とファイル名を提示して、改めて許可をいただく。
- **D4 (決定)** RSS の XML 出力は、RSS 2.0 として等価であればよい (案 B)。差は models.md に記録する。ただし `guid` と `pubDate` の形式は、購読者の RSS リーダーの重複判定に効くので、Python 版と同一にする。
