# モデルと RSS 2.0 出力の仕様 (Rust 版)

作成日: 2026-11-03
状態: ドラフト (レビュー待ち)。承認までは足場・テスト・実装に着手しない。
親仕様: [pipeline.md](pipeline.md) の G-4 (時刻は引数で渡す)、D4 (RSS 2.0 として等価。ただし `guid` と `pubDate` の形式は Python 版と同一)。

## 1. 目的と範囲

記事とフィードの型、および RSS 2.0 の XML への書き出しを定める。通信と HTML 解析は含まない。純粋な変換 (入力が同じなら出力が同じ) にする。

## 2. Python 版の出力 (観察した事実)

`RSSFeed.to_xml()` (`feedgenerator.Rss201rev2Feed`) を、2026-11-03 に実際に動かして確認した。

- 先頭は `<?xml version="1.0" encoding="utf-8"?>` と改行 1 つ。続けて `<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">`。`atom:` の要素は出力されない (名前空間の宣言だけ)。
- 整形 (インデント・改行) はしない。末尾は `</channel></rss>` で、改行はない。
- チャンネルの子要素の順序は `title`、`link`、`description`、`lastBuildDate`、続いて `item` 群。
- `item` の子要素の順序は `title`、`link`、`description`、`pubDate`、`guid`。`pubDate` と `guid` は値がなければ要素ごと出ない。
- `guid` に `isPermaLink` 属性は付かない。
- 空の文字列の要素は `<description/>` と自己閉じになる。
- テキストのエスケープは `&` `<` `>` のみ。`"` と `'` はそのまま。本文中の改行もそのまま。
- 日時は `Tue, 03 Nov 2026 09:30:00 -0000` の形 (曜日・月は英語、日は 0 埋め)。タイムゾーンなし (naive) の値は `-0000`、タイムゾーン付きの値は `+0900` のようにそのオフセットで出る。
- **`lastBuildDate` は、`RSSFeed.last_build_date` の値を使っていない。** 記事の `pub_date` の最大値が使われる。記事がない、または日付がなければ、出力時の現在時刻 (UTC) になる。
- 本文に XML 1.0 で使えない制御文字があると、`UnserializableContentError` で**生成全体が失敗する** (API では 500)。
- タイムゾーン付きと付かない `pub_date` が 1 つのフィードに混ざると `TypeError` で失敗する。実運用では、1 回の生成の中で混ざらない。

**e2 のタイムゾーンは JST** (確認済み)。HTML パーサは `pub_date = datetime.now()` (タイムゾーンなし) を入れるので、コードからの推論では、`pubDate` は「日本時間の時刻に `-0000` が付いた値」で出ている。つまり UTC として読むと 9 時間先の未来になる。(出力そのものでは未確認。確認に使った記事の取得が 0 件だったため。)

## 3. 要件

### M-1 型

```rust
pub struct RssItem {
    pub title: String,
    pub description: String,
    pub link: String,
    pub pub_date: Option<DateTime<FixedOffset>>,
    pub guid: Option<String>,
}

pub struct RssFeed {
    pub title: String,
    pub description: String,
    pub link: String,
    pub items: Vec<RssItem>,
}
```

Python 版の `last_build_date` フィールドは持たない。出力で使われていないため (M-8)。

### M-2 出力関数

**Event**: フィードを XML にするとき
**Response**: `RssFeed::to_xml(&self, now: DateTime<FixedOffset>) -> String`。現在時刻は引数で受け取る (G-4)。内部で時計を読まない。

### M-3 構造

Python 版 (2 章) と同じ構造で書き出す。整形せず、宣言の後の改行 1 つ以外に空白を足さない。要素の順序と、`pubDate` / `guid` の省略規則も同じ。`atom` の名前空間の宣言も、そのまま出す (golden テストでバイト単位に比較できるようにするため)。

### M-4 空要素

テキストが空の要素は `<description/>` のように自己閉じにする。

### M-5 エスケープ

テキストは `&` → `&amp;`、`<` → `&lt;`、`>` → `&gt;` のみ。他の文字は変えない。

### M-6 使えない文字の除去

XML 1.0 で使えない文字は、出力の前に取り除く。対象は `U+0000`〜`U+0008`、`U+000B`、`U+000C`、`U+000E`〜`U+001F`、`U+FFFE`、`U+FFFF`。(`U+0009`、`U+000A`、`U+000D` は残す。)

**Why**: スクレイピングした本文には、まれに制御文字が混ざる。Python 版は 1 文字で生成全体が失敗するが、Rust 版は他の記事を巻き込まない。

### M-7 日時の形式

`pubDate` と `lastBuildDate` は `曜日(英語3文字), 日(0埋め2桁) 月(英語3文字) 年 時:分:秒 ±hhmm`。例: `Tue, 03 Nov 2026 09:30:00 +0900`。値のオフセットはそのまま使う。

### M-8 `lastBuildDate`

記事の `pub_date` のうち最大の値 (オフセットもその記事のもの)。`pub_date` を持つ記事がなければ、`now`。

### M-9 並びと件数

`items` は渡された順のまま出す。件数の制限と並べ替えは、この変換では行わない (パーサとパイプラインの責務)。

### M-10 値の検査はしない

`link` などの URL は文字列のまま出す。取得先の検査は取得層 (ssrf.md) の責務。

## 4. Python 版との差分

| 項目 | Python 版 | Rust 版 | 影響 |
|------|-----------|---------|------|
| 日時のタイムゾーン | タイムゾーンなしの値を `-0000` で出す。e2 では、日本時間の時刻が UTC 扱いになる (推論) | UTC の正しい値を `+0000` で出す | 切替後の `pubDate` は、推論が正しければ 9 時間早くなる。`guid` が同じ形式なので、購読者側の重複判定には影響しない見込み |
| 制御文字 | 生成全体が失敗 (500) | 取り除いて続行 (M-6) | 改善 |
| タイムゾーンの混在 | `TypeError` で失敗 | 型で表現でき、失敗しない | 改善 |
| `last_build_date` | フィールドはあるが出力で未使用 | フィールドを持たない | なし |
| 空要素・エスケープ・要素順・属性 | | 同一 | なし |

**既知の引き継ぎ (変更しない)**: HTML パーサの `guid` は `{base_url}#heading-{i}` のように位置で決まる。記事が前後にずれると、購読者の RSS リーダーでは別の記事と判断される。これは Python 版の挙動で、切替時に既存の購読者が過去の記事を再表示しないよう、同じ形式を保つ。見直しは parser.md で扱う。

## 5. 実装方針 (KISS)

- XML は手書きで組み立てる (数十行)。`rss` クレートは使わない。空要素の自己閉じと `-0000` 以外の同一性を保つには、手書きの方が単純で確実なため。
- 日時は `chrono` (`DateTime<FixedOffset>`)。書式は `%a, %d %b %Y %H:%M:%S %z`。`to_rfc2822()` は日を 0 埋めしないので使わない。

## 6. テスト表 (RED を先に作る)

Python 版の実際の出力を期待値にする。日時の `-0000` だけは `+0000` に置き換える (M-7、4 章)。

**ケース A: 記事 2 件、日時あり**

入力: チャンネル `title = T & <b>"title"</b>`、`description = "説明 あ & <p>x</p>\n改行"`、`link = https://example.com/`。記事 1: `title = 記事1 & <x>`、`description = 本文 "q" 'a' <b>`、`link = https://example.com/a?x=1&y=2`、`pub_date = 2026-11-03 09:30:00 +0000`、`guid = https://example.com/#heading-0`。記事 2: `title = older`、`description = d`、`link = https://example.com/o`、`pub_date = 2026-11-01 01:02:03 +0000`、`guid = g2`。

期待 (1 行):

```
<?xml version="1.0" encoding="utf-8"?>\n<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel><title>T &amp; &lt;b&gt;"title"&lt;/b&gt;</title><link>https://example.com/</link><description>説明 あ &amp; &lt;p&gt;x&lt;/p&gt;\n改行</description><lastBuildDate>Tue, 03 Nov 2026 09:30:00 +0000</lastBuildDate><item><title>記事1 &amp; &lt;x&gt;</title><link>https://example.com/a?x=1&amp;y=2</link><description>本文 "q" 'a' &lt;b&gt;</description><pubDate>Tue, 03 Nov 2026 09:30:00 +0000</pubDate><guid>https://example.com/#heading-0</guid></item><item><title>older</title><link>https://example.com/o</link><description>d</description><pubDate>Sun, 01 Nov 2026 01:02:03 +0000</pubDate><guid>g2</guid></item></channel></rss>
```

(`\n` は実際の改行。)

| ケース | 入力 | 期待 |
|--------|------|------|
| B: オフセット保持 | 記事 1 件、`pub_date = 2026-11-03 09:30:00 +0900`、`guid = g-aware` | `pubDate` も `lastBuildDate` も `Tue, 03 Nov 2026 09:30:00 +0900` |
| C: 日付・guid なし | 記事 1 件 (`title = no guid / no date`、`description = ""`)。`now = 2026-11-03 00:20:53 +0000` | `lastBuildDate` は `Tue, 03 Nov 2026 00:20:53 +0000`。記事は `<description/>` で、`pubDate` と `guid` の要素は出ない |
| D: 記事なし | `now` は C と同じ | `<description/>` と `lastBuildDate` (`now`) のみのチャンネル。`</channel></rss>` で終わる |
| E: 制御文字 | 記事の `title = a\u{1}b é`、他に有効な記事 1 件 | `title` は `ab é`。他の記事も出力される |
| F: 最大値の選択 | `pub_date` が 2 件 (古い方が先頭)、1 件は日付なし | `lastBuildDate` は 2 件のうち新しい方 |
| G: 日の 0 埋め | `pub_date = 2026-01-05 00:00:00 +0000` | `Mon, 05 Jan 2026 00:00:00 +0000` |
| H: エスケープの範囲 | `title = "a" 'b' & <c> >` | `"a" 'b' &amp; &lt;c&gt; &gt;` (引用符は変えない) |

## 7. 未決事項

- **M-6 の扱い**: 取り除く (推奨) か、`U+FFFD` に置き換えるか。どちらでも XML は有効になる。取り除く方が単純。
- **`pubDate` の切替時の変化**: 推論が正しければ 9 時間早くなる。Python 版の「日本時間を UTC 扱い」の値を再現する案もあるが、誤った値を引き継ぐことになるので推奨しない。
- 推論の裏づけ: 実際の `pubDate` が JST の時刻で出ているかを、取得 0 件でなかった記事で確認したい。確認する場合は、e2 の本番サービスに対して追加のリクエストを送ることになるので、実行前に対象 URL を提示して許可をいただく。
