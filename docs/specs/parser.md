# HTML パーサ仕様 (Rust 版)

作成日: 2026-11-03
状態: ドラフト (レビュー待ち)。承認までは足場・テスト・実装に着手しない。
親仕様: [pipeline.md](pipeline.md)。移植元: Python 版 `feedgen/core/parser.py` と `url_normalizers.py`。

## 1. 目的と範囲

HTML 文字列から、メタデータ (タイトル・説明) と記事一覧を取り出す。通信は含まない (取得は ssrf.md の取得層)。純粋な変換にする (G-4)。

```rust
pub fn parse(html: &str, base_url: &str, max_items: usize, now: DateTime<FixedOffset>)
    -> (Metadata, Vec<RssItem>)
```

Python 版は、HTML の解析自体では例外を出さない (`html.parser` は壊れた HTML も受け付ける)。Rust 版も `Result` を返さない。

e2 の実測では、本番の取得先の約 98% がこのパーサ (汎用 HTML 解析) を使う。出力の品質が、そのまま本番の品質になる。

## 2. Python 版の挙動 (BeautifulSoup 4.15.0、`html.parser` を実測)

### 2.1 メタデータ

- `title`: 最初の `<title>` 要素の文字列を `strip()`。要素が**ない**ときだけ `無題`。空の `<title></title>` は空文字列のまま。
- `description`: `<meta name="description">` の `content` が空でなければ、それを `strip()`。`content` が空・属性なし・メタなしのときは、最初の `<p>` の文字列を `strip()` して先頭 200 文字に切り、**必ず** `...` を付ける。空の `<p>` なら `...` だけになる。`<p>` もなければ空文字列。
- `link`: 引数の URL そのまま。

### 2.2 記事の抽出 (3 つの戦略を順に試す)

共通: `max_items` を超えたら打ち切る。文字数は文字 (コードポイント) で数え、切り詰めも文字単位。

**戦略 1: 見出し** (`h1`〜`h6`)
- 文書順の先頭 `max_items × 2` 個の見出しを対象にする (入れ子の見出しも数える)。
- 各見出しについて、子孫の最初の `<a>` を探す。`href` が空・なしなら、その見出しは捨てる (次の `<a>` は探さない)。見出しの外側を包む `<a>` は対象外。
- `title` は見出しの文字列を `strip()`。空なら捨てる。
- `description` は 2.4 の規則。
- `guid` は `{base_url}#heading-{i}`。`i` は**対象にした見出しの文書順の番号** (捨てた見出しも数える)。
- `pub_date` は `now`。

**戦略 2: カード** (記事数が足りないとき、不足分 `remaining` について)
- セレクタを次の順に試す: `[class*="content"]`、`[class*="card"]`、`[class*="cursor-pointer"]`、`article`、`[class*="item"]`。`class` 属性値の部分一致で、大文字小文字は区別する。
- セレクタごとに、先頭 `remaining × 2` 個を対象にし、`remaining` 件に達したら打ち切る。
- 要素の文字列 (`strip()` 後) が 10 文字未満なら捨てる。
- `title`: 要素の子孫の最初の見出しがあればその文字列 (`strip()`、**空でもそのまま採用**)。なければ、文字列を `\n` で分けた各行 (`strip()` 後) のうち、5 文字より長く 200 文字より短い最初の行。それもなければ、先頭 100 文字 (超えるときは `...` を付ける)。
- `description`: 文字列が 200 文字を超えるなら先頭 200 文字 + `...`、以下ならそのまま。
- `link`: 子孫の最初の `<a>` の `href` が空でなければそれ。そうでなければ、要素自身の `data-href`、`data-url`、`data-link` の順。どれもなければリンクなし。
- `title` が空でなく、かつ (リンクがある、または `title` が 5 文字より長い) ときに採用する。リンクがなければ `base_url` を使う。
- `guid` は `{base_url}#card-{採用済みの件数}`。
- 同じ要素が複数のセレクタに一致すると、重複して採用される (後段の重複排除で消える)。

**戦略 3: コンテンツブロック** (まだ足りないとき)
- 文書順の先頭 `remaining × 3` 個の `<p>` と `<div>` を対象にする。
- 文字列 (`strip()` 後) が 30 文字未満なら捨てる。子孫の最初の `<a>` に `href` がなければ捨てる。
- `title` は文字列を `\n` で分けた最初の行の先頭 100 文字。`description` は戦略 2 と同じ。`guid` は `{base_url}#content-{i}` (`i` は対象にしたブロックの番号)。

**重複排除**: `title` を `strip()` して小文字にした値で、最初の 1 件だけ残す。空は捨てる。最後に `max_items` 件に切る。

### 2.3 文字列の取り出し (`get_text()`)

- 子孫のテキストを区切りなしで連結する。コメントは含まない。
- **`<script>`、`<style>`、`<template>` の中身は含まない。`<rt>`、`<rp>` (ルビの読み・括弧) も含まない。** (実測: `a<script>…</script><style>…</style><template>T</template>b<ruby>漢<rp>(</rp><rt>かん</rt><rp>)</rp></ruby>` → `ab漢`)
- 実体参照は文字に直す。未知の名前 (`&unknown;`) は `;` が落ちる (`&unknown`)。
- `strip()` は、Python の空白の定義で両端を削る。`\xa0` (NBSP) は落ちる。`\x1c`〜`\x1f` も落ちる。

### 2.4 見出しの説明 (`_get_description_for_element`)

1. 見出し**自身の子孫を含む**、文書順で次の `<p>` または `<div>` を探す (見出しの中に `<div>` があれば、それが先に見つかる)。見つかれば、その文字列を `strip()`、200 文字を超えるなら先頭 200 文字 + `...`。
2. 見つからなければ、親要素の文字列が見出しの文字列で始まるとき、その残りを `strip()` して同じ切り方。そうでなければ空文字列。

### 2.5 HTML の木の作り方

`html.parser` は HTML5 の規則で木を直さない。実測: `<div><p>one<div>two</div>three</p><p>four<p>five</p></div>` では、`<p>` が 3 個になり、最初の `<p>` の文字列は `onetwothree`、2 つ目は `fourfive` (`<p>` の中に `<p>` が入れ子になる)。HTML5 の解析 (scraper の `html5ever`) では、`<p>` の途中の `<div>` や次の `<p>` で `<p>` が自動で閉じ、別の木になる。

### 2.6 URL の正規化 (`url_normalizers.py`)

- 既定: `http` で始まる `href` はそのまま。`/` で始まるなら `{scheme}://{host}{href}`。それ以外は `{base_url の末尾の / を除いたもの}/{href の先頭の / を除いたもの}`。
  - 例の問題: `//cdn.example.com/x` → `https://host//cdn.example.com/x`。`?page=2` や `#x`、`mailto:`、`javascript:void(0)` → `{base}/?page=2` などの無意味な URL。`base_url` が `…/index.html` のとき、相対パス `a.html` → `…/index.html/a.html`。
- サイト別: Google News (`./articles/`、`./read/` を `news.google.com` のルートへ、デコードは任意)、YouTube、Instagram。ルート相対の `href` を各サイトのオリジンに付ける。**ルート相対については、既定と結果が同じ**。

## 3. 要件 (EARS)

### P-1 木の作り方

**Event**: HTML 文字列が渡されたとき
**Response**: HTML5 準拠のパーサ (`scraper`) で 1 回だけ解析し、同じ木をメタデータと記事の抽出の両方に使う。

壊れた HTML での木の違い (2.5) は、解消しない。Python の `html.parser` を真似るための木の構築器は作らない。違いは golden テストで検出し、仕様の「既知の差」(6 章) に記録する。

### P-2 文字列の取り出し

**Response**: 2.3 のとおり。`script` / `style` / `template` / `rt` / `rp` の中身とコメントを含めず、区切りなしで連結する。両端の空白除去は、Python の `str.strip()` と同じ文字集合 (`char::is_whitespace` に `\x1c`〜`\x1f` を加えたもの) で行う。

### P-3 メタデータ

**Response**: 2.1 のとおり。`無題` は `<title>` 要素がないときだけ。説明の `...` は、最初の `<p>` を使うときは必ず付ける。

### P-4 記事の抽出

**Response**: 2.2 のとおり。戦略の順序、しきい値 (10 / 30 / 5 / 100 / 200)、セレクタの順序、`guid` の番号づけ、重複排除を、Python 版と同じにする。数・切り詰めは文字 (`char`) 単位。

### P-5 時刻

**Response**: すべての記事の `pub_date` は、引数の `now` をそのまま入れる (G-4)。

### P-6 URL の正規化 (Python 版との差あり。決定待ち。7 章 D-P2)

**Response**: `href` は、基準 URL に対して `Url::join` で解決する。`http` / `https` 以外のスキーム (`javascript:`、`mailto:`、`tel:` など) になる `href` は「リンクなし」として扱う。サイト別の正規化クラスは作らない。

| 入力 (基準 `https://h.example/a/index.html`) | Python 版 | Rust 版 (P-6) |
|---|---|---|
| `/x` | `https://h.example/x` | 同じ |
| `https://o.example/y` | そのまま | 同じ |
| `b.html` | `…/index.html/b.html` (誤り) | `https://h.example/a/b.html` |
| `//cdn.example/z` | `https://h.example//cdn.example/z` (誤り) | `https://cdn.example/z` |
| `?p=2` | `…/index.html/?p=2` (誤り) | `https://h.example/a/index.html?p=2` |
| `#top` | `…/index.html/#top` (誤り) | `https://h.example/a/index.html#top` |
| `javascript:void(0)` | `…/index.html/javascript:void(0)` (誤り) | リンクなし |

「リンクなし」の扱いは、戦略 1 では見出しを捨て、戦略 2 では `base_url` を使い、戦略 3 では捨てる (2.2 と同じ)。

### P-7 サイト固有の処理

**Response**: Google News のデコードと、サイト別の URL 正規化は移植しない (e2 の実測で利用 0)。

## 4. 実装方針 (KISS)

- 木の走査は、`scraper` の `Html` と `ElementRef` をそのまま使う。独自の木は作らない。
- 戦略ごとに 1 つの関数、`get_text` と `strip` と切り詰めは共通の小さな関数にする。
- `find_next` (2.4) は、「文書順で、自分の子孫を含む次の要素」を返す関数として 1 か所に実装する。

## 5. テスト方針 (golden / 差分テスト)

出力が外部に配信されるので「必須」の対象。ただし、実 HTML の取得を伴うテストは重い種類なので、まず**合成した小さな HTML** で足りるものを足す。

1. **合成フィクスチャ**: 2 章の実測の各ケース (2.3 の `get_text`、2.5 のネスト、2.4 の `find_next`、`href` が空、空の見出し、`class` の部分一致と大文字小文字、実体参照、閾値の境界、`...` の付き方、重複排除) を、小さな HTML にする。期待値は、Python 版 (main) の出力を使う。
2. **生成の仕組み**: `tools/gen_golden.py` が、HTML ファイルを読み、時刻を固定して Python 版のパーサを動かし、期待値を JSON に書く。期待値の JSON と HTML は、`crates/feedgen-core/tests/fixtures/` に置いてコミットする。Rust のテストは、JSON を読んで、同じ HTML を解析した結果と比べる。
3. **実サイトのフィクスチャ**: e2 の主な 3 ブログと市のサイトの記事一覧ページ (4 件) を取得し、同じ手順で比べる。取得は外部通信とダウンロードにあたるので、**実行前に、取得先 URL・保存するファイル名・想定サイズを提示して許可をいただく**。著作物の転載にあたらないよう、リポジトリには記事一覧の周辺だけに切り詰めた HTML を置くか、リポジトリには置かず、手元だけで実行する (どちらにするかも、許可の際に決める)。
4. 差が出た箇所は、(a) Rust 側を Python に合わせる、(b) Python 側が不具合なら、差を 6 章に記録して Rust は正しい方にする、のどちらかを選ぶ。

## 6. 既知の差 (実装時に追記する)

| 項目 | Python 版 | Rust 版 | 状態 |
|------|-----------|---------|------|
| 壊れた HTML の木 (`<p>` の入れ子など) | `html.parser` のまま | HTML5 の規則 | 受け入れ。golden で検出して追記 |
| 未知の実体参照 `&unknown;` | `;` が落ちる (実測) | `&unknown;` のままのはず (html5ever。**未検証**) | 受け入れ (まれ)。実装時に確認 |
| `<![CDATA[x]]>` | 中身が文字列に入る (実測) | コメント扱いで入らないはず (html5ever。**未検証**) | 受け入れ (まれ)。実装時に確認 |
| URL の正規化 | 2.6 の誤りを含む | P-6 | D-P2 の決定待ち |

## 7. 未決事項

- **D-P1** 壊れた HTML の木の違いは受け入れる (P-1)。この方針でよいか。
  - 補足: e2 の取得先のうち、ブログ (livedoor 系などの古い形式) で `<p>` が閉じていない場合に差が出る可能性がある。実サイトのフィクスチャで確かめる。
- **D-P2** URL は `Url::join` で正しく解決し、Python 版の誤り (2.6) は引き継がない (P-6)。`<link>` の値が変わる記事が出る可能性がある (誤った URL が正しい URL になる)。この方針でよいか。
  - 推奨: 引き継がない。`guid` は URL に依存しないので、購読者の重複判定には影響しない。
- **D-P3** `javascript:` などのスキームは「リンクなし」とする (P-6)。この方針でよいか。
- **D-P4** 実サイトのフィクスチャを取得してよいか。許可は、実行前に取得先とファイル名を提示して、改めていただく (5 章 3)。
  - 保存方法: リポジトリには切り詰めた HTML を置くか、置かないかも決めたい。
- **D-P5** Python の `strip()` と同じ空白の集合 (`\x1c`〜`\x1f` を含む) にそろえる (P-2)。実害はほぼないが、同一性を保つ方が単純。この方針でよいか。
