# YouTube 検索 URL の仕様 (Rust 版)

作成日: 2026-11-06
状態: ドラフト (レビュー待ち)。承認までは、テストと実装に着手しない。
関連: [pipeline.md](pipeline.md) (G-2 の流れ)、[ssrf.md](ssrf.md)、[api.md](api.md)。Issue: `densuke/Agy-Virtual-Office#910` (判断は #890)。
移植元: Python 版 `feedgen/core/youtube_client.py`、`feedgen/core/generator.py` の `_generate_youtube_feed`。

## 1. 目的と範囲

YouTube の検索結果の URL を、YouTube Data API (v3) の検索で、動画のフィードにする。

- **現状**: Rust 版は、この URL を一般の処理に回し、**HTTP 200 で記事 0 件のフィード** (題は「無題」) を返す。エラーにもならず、購読が静かに空になっている (2026-11-06 に、手元の CLI で確認)。
- **呼び出し**: 毎日 19:20 に、同じ検索 URL を、Google のアドレス帯が 1 回取得している (e2 の Caddy ログ、11-03〜11-06 の 3 件)。

対象外: チャンネル、再生リスト、動画そのもの、`www.youtube.com` 以外のホスト、API の結果のキャッシュ (#891 で不要と判断)。

## 2. Python 版の挙動 (互換の基準)

- 対象の判定: ホストが `www.youtube.com` と完全一致、パスが `/results`、クエリに `search_query` がある。
- API: `search.list` (`part=snippet`、`type=video`、`order=relevance`、`maxResults` は 1〜50 に丸める)。検索 URL の `sp` などは使わない。
- フィード: 題 `YouTube検索: {検索語}`、説明 `YouTube検索「{検索語}」の結果`、link は入力の URL。
- 記事: title (なければ「無題」)、link `https://www.youtube.com/watch?v={id}`、**guid `youtube-video-{id}`**、pubDate は `publishedAt` (解釈できなければ現在時刻)、説明は、300 文字を超えたら切って `...` を付け、チャンネル名があれば `チャンネル: {名前}\n\n` を先頭に付ける。`videoId` のない結果は飛ばす。
- API が失敗したときは、ページを取得して HTML 解析に落ちる (実際には、YouTube の検索ページは、JavaScript で描画されるため、空に近い)。キーがないときも、同じ。

## 3. 要件 (EARS)

### Y-1 対象 URL の判定

**Event**: `generate` が URL を受けたとき
**Response**: 次をすべて満たす URL を、YouTube の検索 URL とする。(1) スキームが `http` か `https`。(2) ホストが `www.youtube.com` (大文字小文字を区別しない。ポートは既定のみ)。(3) パスが `/results`。(4) クエリに、空でない `search_query` がある (同じ名前は先頭の値)。判定は、**入力の URL に対して、取得より前**に行う。満たさなければ、従来の流れ (G-2) のまま。

### Y-2 取得の省略

**Response**: YouTube の検索 URL では、`www.youtube.com` のページを取得しない。`use_feed` と `feed_first` は無視する (`detected` は空)。結果は `Outcome::Generated`。

### Y-3 API の呼び出し

**Response**: 次を、既存の取得層 (SSRF 対策。ssrf.md) を通して取得する。取得先のホストは固定で、入力に由来しない。

`GET https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&order=relevance&maxResults={n}&q={検索語}&key={キー}`

- `n` = `max_items` を 1〜50 に丸めた値。
- 検索語とキーは、URL エンコードして入れる。
- `User-Agent` は、呼び出し元から渡されたもの。
- ステータスが 200 のときだけ成功。

### Y-4 記事の作り方

**Response**: 応答の `items` を、**API の順に**、次のとおり記事にする。`id.videoId` がないものは飛ばす。

| 項目 | 値 |
|---|---|
| title | `snippet.title` (なければ「無題」) |
| link | `https://www.youtube.com/watch?v={videoId}` |
| guid | `youtube-video-{videoId}` (**Python 版と同じ。購読者の既読管理を壊さないため**) |
| pubDate | `snippet.publishedAt` (RFC 3339)。なし、または解釈できないときは、呼び出し時に渡された現在時刻 |
| description | `snippet.description` が 300 文字を超えたら、300 文字に切って `...` を付ける。`channelTitle` があれば、`チャンネル: {名前}\n\n` を先頭に付ける (説明がなければ `チャンネル: {名前}` のみ) |

**Python 版との差 (直す)**: API の文字列に含まれる **HTML の文字参照** (`&amp;`、`&#39;` など) を、記事に入れる前に復号する。Python 版は、そのまま入れたため、XML に出すとき、二重にエスケープされていた。

### Y-5 フィード

**Response**: title は `YouTube検索: {検索語}`、description は `YouTube検索「{検索語}」の結果`、link は**入力の URL そのまま**。結果が 0 件でも、200 で、空のフィードを返す (API が成功した場合のみ)。

### Y-6 API キー

**Response**:
- キーは、環境変数 `YOUTUBE_API_KEY` から、**サーバーと CLI が起動時に 1 回**読み、`FeedGenerator` に渡す。空文字は、未設定として扱う。
- キーは、ログ、エラーの本文、`Debug` の出力、フィード、リポジトリに**出さない**。(`Debug` では、伏せ字にする。)
- キーを URL に付けるので、取得層のエラーが URL を含まないことを、テストで固定する (現状は、固定の文言)。

### Y-7 エラー

**Response**: `FeedError::YouTube(String)` を足す (API 層では、A-4 のとおり 400)。文言は、キーも、API の応答の本文も含まない。

| 状況 | 文言 |
|---|---|
| キーが未設定 | `YouTube の検索には API キーの設定が必要です` |
| 403 で、理由が `quotaExceeded` | `YouTube API のクォータを超過しました` |
| 理由が `keyInvalid` / `API_KEY_INVALID` (400 か 403) | `YouTube API キーが無効です` |
| ほかの 200 以外、または JSON として読めない | `YouTube API の呼び出しに失敗しました (HTTP {n})` |
| 取得層の失敗 (通信、締切、SSRF の拒否) | 既存のエラーのまま (`Http` / `UnsafeUrl`) |
| 呼び出しの上限 (Y-8) | `YouTube の検索の上限に達しました。時間をおいて再度お試しください` |

**Python 版との差**: Python 版は、キーがない、または API が失敗すると、HTML 解析に落ちて、(ほぼ空の) フィードを返していた。Rust 版は、**空のフィードを返さず、エラーにする** (購読が静かに空になるのを防ぐ。Issue #910 の要件)。

### Y-8 呼び出しの予算 (クォータの保護)

**Response**: プロセス全体で、**直近 24 時間 (スライディング) に、API を呼べるのは 30 回まで**。超えたら、API を呼ばず、Y-7 の「上限」のエラーにする。数えるのは、API の呼び出しを始めたときで、成否を問わない。再起動で、カウントは 0 に戻る。

**Why**: `/feed` は、認証なしで公開されている。`search.list` は 1 回 100 ユニットで、1 日の既定の割り当ては 10,000 ユニット (= 100 回)。第三者が、検索 URL を並べて呼ぶだけで、正規の購読 (1 日 1 回) の分まで、クォータを使い切れてしまう。30 回は、実測 (1 日 1 回) の 30 倍で、割り当ての 30%。

**注意**: 予算が尽きている間は、正規の購読も 400 になる。攻撃が続けば、購読は止まるが、クォータが尽きて Google 側で 403 になる (どちらでも止まる) より、API キーが止められる (ブロックされる) 危険が小さい。

### Y-9 そのほか

- API の結果は、キャッシュしない (#891)。
- 検索語の長さは、`url` の上限 (api.md A-2、2048 文字) の範囲内。API に渡す前に、追加の検査はしない (API が拒否する)。

## 4. 実装方針 (KISS)

- `crates/feedgen-core/src/youtube/` を新設する: `mod.rs` (判定と流れ)、`api.rs` (URL の組み立て、応答の解釈、エラーの対応、記事の作成)、`budget.rs` (予算)。取得は、既存の `SafeFetcher` を使う。
- `FeedGenerator` に、`with_youtube_api_key(Option<String>)` を足す。キーは、`Debug` で伏せ字になる小さな型に入れる。
- `generate` の先頭 (取得の前) で、Y-1 の判定を行い、該当すれば、YouTube の流れに進む。
- JSON の解釈は `serde_json` を使う (すでに開発用の依存にある。本番の依存に格上げする)。文字参照の復号は、既存の HTML 解析のライブラリ (`scraper`) を使う。
- 取得先のホストは定数で、テストのときだけ、ローカルの偽サーバーに差し替える (本番に、取得先を変える口を作らない。ssrf.md S-10)。
- 時刻は、これまでどおり、呼び出し側から受け取る。予算は、時計を注入できるようにして、テストでスライディングの境界を確かめる。
- サーバーと CLI は、起動時に環境変数を読むだけ (配線のみ)。e2 では、`feedgen-rs.service` に `EnvironmentFile=-/etc/default/feedgen-rs` を足し、そこにキーを置く (モード 0600)。

## 5. テスト方針

- **判定** (表。軽い): Y-1 の各条件 (ホストの大文字小文字、`m.youtube.com` や `youtube.com` は対象外、パス違い、`search_query` なし・空・重複、スキーム違い、ポート)。
- **API の URL の組み立て**: 丸め (0 → 1、100 → 50)、エンコード (日本語、`&`、`=`、空白)、キーのエンコード。
- **応答の解釈** (表): 通常、`videoId` なしを飛ばす、title なし → 「無題」、説明の 300 文字の境界と `...`、チャンネル名の有無 (説明あり、なし)、`publishedAt` の不正 → 現在時刻、文字参照の復号 (`&amp;`、`&#39;`、`&quot;`)、空の `items`、JSON として不正、`items` が配列でない。
- **エラーの対応**: Y-7 の表の各行 (403 `quotaExceeded`、`keyInvalid`、500、不正な JSON)。**どの文言にも、キーが含まれない**こと。
- **予算** (時計を注入): 30 回目までは通り、31 回目で拒否、24 時間後に、古い分が数えられなくなる。拒否のときは、API を呼ばない (偽サーバーのリクエスト数で確かめる)。
- **パイプライン** (ローカルの偽サーバー。実ネットワークなし): `www.youtube.com` のページを取得しない、guid と link と題、キー未設定で、**リクエストが 1 回も発生しない**、API の失敗でエラー (空のフィードにならない)、`use_feed` を付けても、同じ。キーが、エラーにも `Debug` にも出ない。
- **API 層**: `FeedError::YouTube` が 400 で、`{"detail": …}` になる (偽の `FeedService`)。
- **サーバー、CLI の起動**: 環境変数を読むだけの配線は、テストしない (理由は README に書く)。

## 6. 配備

1. 版を `0.2.0` に上げる (機能の追加。タグ付きリリースが作られる。release.md R-2)。
2. マージ後、リリースが作られたら、e2 で `/etc/default/feedgen-rs` (0600) に `YOUTUBE_API_KEY` を置く。**Python 版の `.env` の同じ行を、画面に出さずに、コピーする** (キーを、チャット、ログ、コミットに出さない)。ユニットに、`EnvironmentFile=-/etc/default/feedgen-rs` を足して、`daemon-reload` する。
3. `update.sh` で更新する (`feedgen-rs.service` が再起動する)。
4. e2 の中から、検索 URL で `/feed` を叩き、動画が入ることを確かめる。キーが、`journalctl` に出ていないことも確かめる。
5. 翌日 19:20 の、定期の呼び出しが、200 で動画のあるフィードを受け取ったことを、Caddy のログで確認する。

## 7. Python 版との差

| 項目 | Python 版 | Rust 版 | 状態 |
|---|---|---|---|
| 並び (`order`) | `relevance` | 同じ | 維持 |
| `sp` などの検索 URL のほかのパラメータ | 無視 | 無視 | 維持 |
| guid | `youtube-video-{id}` | 同じ | **維持** (既読管理) |
| 文字参照 (`&amp;` など) | そのまま (二重エスケープ) | 復号 | 直す |
| キーがない | HTML 解析に落ちる (ほぼ空) | 400 | 直す (静かに空にしない) |
| API の失敗 | HTML 解析に落ちる (ほぼ空) | 400 (理由つき) | 直す |
| クォータの保護 | なし | 24 時間に 30 回 | 追加 |
| `use_feed` / `feed_first` | 無視される (YouTube 優先) | 無視 | 維持 |

## 8. 未決事項 (推奨つき)

- **D-Y1** 並びは `relevance` (Python 互換) のままにする。推奨: この方針。新着順 (`date`) の方が、フィードに向くが、購読の中身が変わるので、別の判断にする。検索 URL の `sp` の意味は解釈しない。
- **D-Y2** 予算は、24 時間に 30 回。推奨: この方針 (割り当ての 30%)。
- **D-Y3** キーがない、または API の失敗は、400 にする (HTML 解析に落ちない)。推奨: この方針 (#910 の要件)。
- **D-Y4** 版を `0.2.0` に上げる。推奨: この方針 (タグ付きリリースを作るため)。
- **D-Y5** 予算が尽きている間は、正規の購読も 400 になる。推奨: 許容する (Y-8 の注意)。変えるなら、検索語の許可リストが要る (複雑になるので、今回はしない)。
