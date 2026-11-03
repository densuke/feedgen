# 既存フィード検出の仕様 (Rust 版)

作成日: 2026-11-03
状態: ドラフト (レビュー待ち)。承認までは足場・テスト・実装に着手しない。
親仕様: [pipeline.md](pipeline.md) の G-2 (処理の順序)、G-3 (取得は取得層を通す)、G-7 (URL 自体がフィード)。取得層は [ssrf.md](ssrf.md)。
移植元: Python 版 `feedgen/core/feed_detector.py` (SSRF 対策のマージ後、`safe_request` を使う版)。

## 1. 目的と範囲

次の 3 つを定める。

1. 取得済みの HTML から、既存フィードの候補を取り出す (`<link rel="alternate">`)。
2. HTML に候補がないとき、サイトのルートにある共通パスを確かめる。
3. 取得した本文が、フィードそのものかを判定する (G-7)。

フィードの本文を取得して返す処理 (代理取得) は、パイプラインの責務 (G-2 の 6)。この仕様は、取得の手段と、本文の判定だけを決める。通信はすべて取得層を通す (G-3)。

```rust
pub fn detect_from_html(html: &str, base_url: &str) -> Vec<FeedInfo>;
pub async fn probe_common_paths<L: Lookup>(fetcher: &SafeFetcher<L>, base_url: &str) -> Option<FeedInfo>;
pub fn feed_root(body: &[u8]) -> Option<RootKind>;
```

## 2. Python 版の挙動 (通信なしで実測。2026-11-03)

### 2.1 HTML の `<link>` (`_detect_from_html`)

| 入力 | 結果 |
|------|------|
| `rel="alternate"` | 検出する |
| `rel="alternate stylesheet"`、`rel="stylesheet alternate"` | 検出する (トークンの一致) |
| `rel="ALTERNATE"`、`rel="Alternate"` | **検出しない** (大文字小文字を区別する) |
| `rel="alternate-x"` | 検出しない |
| `type="application/rss+xml"`、`application/atom+xml`、`application/xml`、`text/xml` | 検出する。大文字や `; charset=utf-8` つきも可 (小文字にして部分一致) |
| `type="application/json"` | 検出する (種類は `JSON`) |
| `type="application/feed+json"` (JSON Feed の正式な MIME タイプ) | **検出しない** |
| `type="text/html"`、空、属性なし | 検出しない |
| `href` が空、なし | 検出しない |
| `href="javascript:x"` | **そのまま URL として返す** |
| `href="  /f  "` | `https://example.com/f  ` (末尾に空白が残る) |
| `href="//cdn.example.org/f"`、`../f.xml`、相対パス | `urljoin` で解決する |
| `title` なし | `不明なフィード` |
| `title=""` | 空文字列のまま。前後の空白もそのまま |
| 複数の `<link>` | 文書順にすべて返す。`use_feed` では**先頭**が使われる |
| `<body>` の中の `<link>` | 検出する (`<head>` に限らない) |
| フィード (RDF) そのもの | 0 件 (`<link>` が `rel="alternate"` を持たない) |

種類の名前 (`RSS`、`Atom`、`JSON`、`XML`) は、`type` の中に `rss`、`atom`、`json` を含むかどうかを、この順に見て決める。それ以外は `XML`。`X-Existing-Feed-Type` ヘッダに、この名前が入る。

実サイト 2 件 (`mfujin.blog.jp`、`kabumatome.doorblog.jp`) の HTML では、どちらも `RSS` (`/index.rdf`) と `Atom` (`/atom.xml`) の 2 件を、この順で検出した。先頭は RDF (RSS 1.0)。

### 2.2 共通パス (`_detect_from_common_paths`)

- 基準は、URL のパスではなく**サイトのルート** (`スキーム://ホスト[:ポート]`)。深い URL でも、ルートの `/feed` などを調べる。
- パスは次の順に、**1 本ずつ**試す。最初に見つかったところで止める。
  `/feed`、`/rss`、`/atom.xml`、`/rss.xml`、`/feed.xml`、`/feeds/all.atom.xml`、`/rss/index.xml`、`/feed/index.xml`
- 1 本は `HEAD` で、締切は 10 秒。ステータスが 400 未満で、`Content-Type` がフィードの型 (2.1 の `type` と同じ部分一致) か、`xml` を含めば「ある」。
- 結果のタイトルは `{ホスト[:ポート]} - {種類}`。種類は **`Content-Type` ではなく、パスから**決まる (パスに `atom` を含めば `Atom`、`json` を含めば `JSON`、それ以外は `RSS`)。
- 実測 (`HEAD` を差し替えて確認):
  - `/feed` が `text/html` で、`/rss` が `application/rss+xml` なら、`/rss` を返す。
  - `/feed` と `/atom.xml` が両方 xml なら、順序の早い `/feed` を返す。
  - 404 や `text/plain` は「ない」。
  - `/feed` が `application/json` なら、`/feed` を**種類 `RSS`** で返す (パスで決まるため)。
  - `HEAD` が 405 を返すサーバーは、「ない」になる。

## 3. 要件 (EARS)

### D-1 HTML の `<link>` からの検出

**Event**: 取得済みの HTML と基準 URL が渡されたとき
**Response**: 次の条件をすべて満たす `<link>` 要素を、文書順に `FeedInfo` にして返す。

- `rel` の値を空白で分けたトークンの 1 つが `alternate` (ASCII の大文字小文字を区別しない)。
- `type` の **media type** が、`application/rss+xml`、`application/atom+xml`、`application/xml`、`text/xml`、`application/json`、`application/feed+json` のどれかと**完全一致**する。media type は、`;` 以降 (パラメータ) を除き、前後の空白を除き、ASCII の小文字にしたもの (`application/rss+xml; charset=utf-8` は `application/rss+xml`)。`application/xml-dtd` や `application/jsonl` のような、前方一致する別の型は拾わない。
- `href` が、前後の **ASCII の空白**を除いて空でない (NBSP などの Unicode の空白は除かない。HTML の URL の扱いと同じ)。
- `href` を基準 URL に対して `Url::join` で解決した結果が、`http` または `https` で、**認証部 (ユーザー名・パスワード) を持たない**。
- 解決した URL から **fragment (`#…`) を除いた**ものが、基準 URL (同じく fragment を除いたもの) と同じでない (`href="#"` や `#top` は、ページ自身を指すので捨てる)。

`<head>` に限らず、文書全体を対象にする。

**種類**は、`type` に `rss` を含めば `Rss`、`atom` を含めば `Atom`、`json` を含めば `Json`、それ以外は `Xml` (この順に判定)。

**タイトル**は `title` 属性の前後の空白を除いたもの。属性がない、または空なら `不明なフィード`。

出力する URL は、fragment を除いたもの。同じ URL (解決後、fragment を除いたもの) が複数あるときは、最初の 1 件だけ残す。

### D-2 検出結果の順序

**Response**: D-1 の結果は文書順のまま返す。パイプラインは、先頭を使う (G-2)。並べ替えや、フィードの内容による選別はしない。

**既知の限界**: WordPress などは、コメントのフィードを投稿のフィードより先に宣言することがある。先頭を使う方針 (Python 版と同じ) では、コメントのフィードが選ばれる。

### D-3 共通パスの確認

**Event**: HTML から候補が見つからず、パイプラインが共通パスの確認を求めたとき
**Response**: 基準 URL のサイトのルートについて、2.2 の 8 本のパスを、**並列に** `HEAD` で確かめる。「ある」と判断したもののうち、**リストの順序で最も早いもの**を 1 件返す。1 件もなければ `None`。

- 各 `HEAD` は取得層を通し (G-3)、さらに 10 秒の締切を外側から付ける。全体の所要時間は、最も遅い 1 本の締切 (最大 10 秒) で決まる (Python 版は最大 80 秒)。
- 「ある」の条件: ステータスが **200**、かつ `Content-Type` の **media type** (`;` 以降のパラメータを除き、小文字にしたもの。パラメータは見ない) が `rss`、`atom`、`xml`、`json` のどれかを含み、**`html` を含まない**。`application/octet-stream; filename=feed.xml` のように、パラメータにだけ `xml` がある値は、フィードとみなさない。
- この判定は**緩い** (`application/rdf+xml` や `application/x-rss+xml` も通す。完全一致にすると、そのようなサーバーを取りこぼす。Python 版は `xml` を含めば通していた)。緩い判定による誤検出 (`application/vnd.api+json` など) は、パイプラインがその後に本文のルート要素で判定する (G-7、D-5) ので、害がない。
- 失敗 (締切、取得層の拒否、通信エラー) は、そのパスを「ない」とする。エラーは返さない (Python 版と同じ)。

**基準 URL**: パイプラインは、リダイレクトを追従した後の最終 URL (`Fetched.final_url`) を渡す。

**Why**: `application/xhtml+xml` は `xml` を含むので、`html` を除外しないと、XHTML を返す全パス共通の応答を、フィードとして拾ってしまう。

### D-4 共通パスで見つけたフィードの種類

**Response**: `Content-Type` で決める (`rss` → `Rss`、`atom` → `Atom`、`json` → `Json`、それ以外は `Xml`)。`Xml` のときだけ、パスで補う (パスに `atom` → `Atom`、`json` → `Json`、それ以外 → `Rss`)。タイトルは `{ホスト[:ポート]} - {種類の名前}`。

### D-5 フィードそのものの判定 (G-7)

**Event**: 本文のバイト列が渡されたとき
**Response**: 本文の**ルート要素**が、次のどれかなら `Some(RootKind)`、それ以外は `None`。

| ルート要素 (名前空間の接頭辞を除いた名前。大文字小文字を区別する) | `RootKind` |
|---|---|
| `rss` | `Rss` (RSS 0.9x / 2.0) |
| `RDF` (`rdf:RDF`) | `Rdf` (RSS 1.0) |
| `feed` | `Atom` |

ルート要素を探すとき、先頭から次を読み飛ばす。
- UTF-8 の BOM
- 空白
- XML 宣言と処理命令 (`<?…?>`)
- コメント (`<!-- … -->`)
- `<!DOCTYPE …>` (内部サブセット `[…]` を含む)

走査するのは、先頭の 64 KiB まで。見つからなければ `None`。UTF-16 などの本文は、判定の対象にしない (`None`)。`Content-Type` は見ない。

**Why**: HTML のページは、先頭が `<!DOCTYPE html>` や `<html` で、ルート要素が `html`。`Content-Type` に `xml` を含む HTML (XHTML) も、ルート要素で区別できる。

### D-6 代理取得の `Content-Type`

**Response**: `proxied_content_type(root, original) -> String`。`Rss` と `Rdf` は `application/rss+xml`、`Atom` は `application/atom+xml`。元の `Content-Type` の `charset` が、`encoding_rs` が知っているラベル (引用符は、二重・単一とも除く) のときだけ、`; charset=…` を引き継ぐ。ないとき、知らないラベルのとき、複数の `Content-Type` をつないだ値 (`utf-8, text/plain` など) のようにラベルとして読めないときは、付けない (本文は変換しないため、XML 宣言の文字コードが生きる)。

### D-7 取得とエラー

**Response**: この仕様の関数は、`probe_common_paths` を除いて通信しない。HTML から見つけた URL (D-1) は、パイプラインが取得層で取得するときに検査される (ssrf.md)。内部アドレスを指していても、この段階では候補に含める。

## 4. 実装方針 (KISS)

- `detect_from_html` は、`scraper` で `link` 要素を走査する純粋な関数。HTML は、パーサ (parser.md) と同じ規則で解析する (スクリプト無効)。
- `rel` のトークン判定は、空白で分けて ASCII の大文字小文字を無視して比べる。CSS セレクタの `~=` は使わず、コードで判定する (大文字小文字の扱いを自分で決めるため)。
- `feed_root` は、バイト列を先頭から読む小さな手書きの走査器にする (XML パーサは使わない)。
- 並列化は、`futures` などの小さな依存か `tokio::task::JoinSet` で足りる。手段は実装時に決める。

## 5. テスト方針

- **表のテスト** (軽い): `detect_from_html` (D-1)、`feed_root` (D-5)、`proxied_content_type` (D-6)。
- **golden** (Python 版との一致): `tools/gen_golden.py` に、検出結果 (`feeds`: URL・タイトル・種類) の書き出しを足す。`_detect_from_html` は取得を `safe_request` 経由で行うので、オラクルでは取得を差し替えて、フィクスチャの HTML を返す。Python 版と挙動を変えた点 (3.D-1 の `rel` の大文字小文字、`application/feed+json`、`javascript:`、`href` の空白、空の `title`、重複 URL) は、手書きの期待値で確認する。実サイト (`real/`) の 2 件も、同じ手順で比べる (ローカルのみ)。
- **共通パス** (重いテストなので、1 つのローカルサーバーで関心をまとめる): 順序 (`/feed` が `text/html` で `/rss` が `rss`)、両方 xml なら早い方、404、`html` を含む `Content-Type` の除外、`HEAD` が 405、種類が `Content-Type` で決まること、並列であること (遅い 1 本が全体を、パスの数だけ遅くしない)、1 本の締切 (10 秒) で打ち切ること。
- **`feed_root` の境界**: BOM、`<?xml?>`、`<?xml-stylesheet?>`、コメント、`DOCTYPE` (内部サブセットつき)、`rss`、`rdf:RDF`、`RDF`、`feed`、名前空間の接頭辞つき `atom:feed`、`<!DOCTYPE html>`、`<html>`、XHTML (`<?xml ?><!DOCTYPE html …><html xmlns=…>`)、空の本文、64 KiB を超えるコメントで始まる本文、UTF-16。
- 実サイトの `assets.wor.jp` の RDF (`real/`、ローカルのみ) が、`Rdf` と判定されること。

## 6. Python 版との差

| 項目 | Python 版 | Rust 版 | 状態 |
|------|-----------|---------|------|
| `rel` の大文字小文字 | 区別する (`ALTERNATE` を検出しない) | 区別しない (HTML の仕様どおり) | 直す |
| `type="application/feed+json"` | 検出しない | 検出する (`Json`) | 直す |
| `href="javascript:x"` など | そのまま返す | `http(s)` 以外は捨てる | 直す |
| `href` の前後の空白 | 残る | 取り除く (`Url::join`) | 直す |
| `title` なし/空 | なし → 既定、空 → 空 | どちらも既定。前後の空白を除く | 直す |
| 重複する URL | 残す | 最初の 1 件だけ | 直す |
| 共通パスの確認 | 1 本ずつ (最大 80 秒) | 並列 (最大 10 秒) | 直す |
| 共通パスの「ある」 | ステータス 400 未満、`xml` を含む (XHTML も通る) | 200 のみ、`html` を含むものを除く | 直す |
| 共通パスの種類 | パスから決める | `Content-Type` から決める | 直す |
| URL 自体がフィード | 検出しない (HTML として解析し 0 件) | ルート要素で判定して代理取得 (G-7) | 直す (決定済み) |
| 先頭のフィードを使う | 先頭を使う | 同じ (D-2) | 維持。既知の限界 |
| `HEAD` が 405 のサーバー | 見つからない | 同じ | 既知の限界 (7 章 D-D2) |
| `href="#"`、`#frag` | fragment つきのまま出す。`#` はページ自身がフィードとして出る | fragment を除く。ページ自身を指すものは捨てる | 直す |
| 認証部つきの URL | そのまま出す (パスワードが結果に残る) | 捨てる | 直す |
| `type` の判定 | 部分一致 (`application/xml-dtd`、`application/jsonl` も通る) | media type の完全一致 | 直す |
| 共通パスの `Content-Type` | パラメータも含めて `xml` を含めば通す | パラメータを除いた media type で、緩く判定 | 直す |
| `href` の空白 | Unicode の空白も、そのまま残る | ASCII の空白だけ除く | HTML の仕様に合わせる |
| 同じ属性が 2 つ (`href=/a href=/b`) | 後のもの (`/b`) | 先のもの (`/a`、ブラウザと同じ) | 受け入れ (html5ever の規則) |
| `DOCTYPE` の内部サブセットの処理命令に、引用符が 1 つだけある | (該当なし) | ルート要素を見つけられず、フィードと判定しない | 既知の限界 (極めて稀) |
| 共通パスの確認の所要時間 | 1 本ずつ (最大 80 秒) | 8 本すべての完了を待つ (最大 10 秒) | 既知の限界 (先に見つかっても、遅いパスを待つ。結果は正しい) |

## 7. 未決事項 (推奨つき)

- **D-D1** JSON Feed は、検出して `detected` には含めるが、`use_feed` の代理取得では返さない (D-5 は XML のルート要素だけ。JSON の本文は `feed_root` が `None` になり、HTML 解析に進む)。推奨: この方針。JSON Feed の利用は、e2 の実測で確認できていない。
- **D-D2** `HEAD` が 405 や 501 を返すサーバーで、`GET` に切り替えて確かめる処理は、今は作らない (YAGNI)。推奨: 作らない。共通パスの確認は、HTML に `<link>` がないときだけの最終手段で、`use_feed` / `feed_first` のときに限られる。
- **D-D3** 先頭のフィードを使う (D-2) 方針を維持する。推奨: 維持する。コメントのフィードが先に宣言されるサイトは、実サイト 2 件には現れなかった。必要になったら、`title` や URL に `comment` を含むものを後ろへ回す規則を、別の判断として足す。
- **D-D4** 共通パスの `HEAD` は、同じホストへ最大 8 本を同時に送る。推奨: 8 本のまま。Python 版は 1 本ずつだが、最大 8 本を送る点は同じで、`use_feed` / `feed_first` のとき、HTML に `<link>` がない場合だけに限られる。同時に送る数を絞る (例: 4 本) 案もある。
