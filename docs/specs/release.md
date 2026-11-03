# 自動ビルドとリリース置き換えの仕様

作成日: 2026-11-03
状態: ドラフト。承認までは、ワークフローとスクリプトの実装に着手しない。
関連: [api.md](api.md) (サーバーと CLI)。前例: `blog-autopost-public` の `ci.yml`、`release.yml`、`dependabot-automerge.yml`。

## 1. 目的と範囲

- main の変更を、GitHub Actions で検査し、Linux 向けの静的バイナリにしてリリースする。
- 依存の更新を、Dependabot が週 1 回提案し、テストが通れば自動で取り込み、新しいリリースにする。
- e2 で、新しいリリースを、検証してから置き換える。異常なら、自動で元に戻す。

対象外: macOS 向けのビルド、Python 側の依存の更新、複数台への配備、Windows。

## 2. 前提

- 配備先は e2 (Ubuntu 24.04、x86_64、メモリ 1GB)。そこではビルドしない。
- 本番の入口は Caddy。Rust 版は `127.0.0.1:8001` で `feedgen-rs.service` として動き、Python 版 (`feedgen.service`、8000) は待機している (置き換えの判断までは残す)。
- 配布物は GitHub のリリース (公開) から、認証なしで取得する。非公開にする場合は、取得にトークンが要る (R-8 の注記)。

## 3. 要件 (EARS)

### R-1 検査 (CI)

**Event**: main への Pull Request、または push
**System**: GitHub Actions (`ci.yml`、`ubuntu-24.04`)
**Response**: `cargo fmt --all -- --check`、`cargo clippy --workspace --all-targets -- -D warnings`、`cargo test --workspace` を実行し、1 つでも失敗したら失敗にする。カバレッジは、サマリを表示するだけで、しきい値では失敗させない (計器として使う)。Dependabot の PR は、R-4 側でテストするので、ここでは除く。

### R-2 ビルドとリリース

**Event**: main への push、または手動の起動
**System**: GitHub Actions (`release.yml`)
**Response**:
1. `x86_64-unknown-linux-musl` 向けに、`feedgen-server` と `feedgen` を、リリースビルドする (ランナー上で `musl-tools` を使う。`cross` と Docker は使わない)。
2. 1 つのアーカイブ (`feedgen-x86_64-unknown-linux-musl-<version>.tar.gz`) にまとめ、`.sha256` を添える。中身は 2 つのバイナリのみ (設定や秘密情報を含めない)。
3. ローリングのプレリリース `latest` を、常に最新のコミットを指すよう作り直す。
4. `Cargo.toml` の `version` に対応するタグ `v<version>` がまだなければ、その版のタグ付きリリースも作る。

**排他**: リリースの処理は、同時に 1 つだけ動かす (連続した push で、競合しないため)。

### R-3 依存更新による版の自動更新

**Event**: main に、コミットメッセージが `deps` で始まる変更 (Dependabot の cargo 更新) が入ったとき。かつ、現在の版のタグがすでにあるとき
**Response**: ワークスペースの版の patch を 1 つ上げ、`Cargo.lock` の自クレートの版も更新して、`[chore]` のコミットを main に push する。これを、新しい版として R-2 の 4 に渡す。`ci` で始まる更新 (Actions の更新) は、バイナリに影響しないので、対象外。

### R-4 Dependabot

**Event**: 毎週月曜 9:00 (JST)
**System**: Dependabot (`dependabot.yml`)
**Response**: cargo の依存 (コミットの接頭辞 `deps`) と GitHub Actions (接頭辞 `ci`) の更新を、PR にする。未処理の PR は 5 件まで。

**Event**: Dependabot の PR が作られたとき
**System**: `dependabot-automerge.yml`
**Response**: PR の先頭で `cargo test --workspace` を実行する。通れば、major 更新以外を、squash でマージする。マージしたら、`release.yml` を、手動の起動 (`workflow_dispatch`) で起動する (トークンによるマージの push は、ワークフローを起動しないため)。失敗した PR と major 更新は、人が見るために残す。

### R-5 e2 の更新の確認

**Event**: `update.sh` が起動されたとき (手動、または R-7 のタイマー)
**System**: e2 の `~/work/feedgen-rs/update.sh`
**Response**:
1. 最新のタグ付きリリースの版を取得する。インストール済みの版 (`VERSION` ファイル) と同じなら、何もせず、終了コード 0 で終わる。
2. 違えば、アーカイブと `.sha256` を、作業用の一時ディレクトリに取得し、チェックサムを検証する。**合わなければ、何も置き換えず、終了コード 1。**
3. アーカイブが、期待する 2 つのバイナリだけを含み、パスに `..` や絶対パスを含まないことを確かめる。

### R-6 置き換えと自動ロールバック

**Event**: R-5 の検証が通ったとき
**Response**:
1. 現在の `feedgen-server` を `feedgen-server.prev` に、`VERSION` を `VERSION.prev` に退避する。
2. 新しいバイナリを、同じファイルシステム上の一時名に置いてから、`mv` で入れ替える (途中で止まっても、半端なファイルが残らない)。
3. `feedgen-rs.service` を再起動し、`http://127.0.0.1:8001/health` が、起動後に、最大 15 秒以内に 200 を返すかを確かめる。
4. **通らなければ**、`.prev` を戻して再起動し、終了コード 1 で終わる。戻したあとの `/health` も確かめる。
5. 通れば、新しい版を `VERSION` に書き、終了コード 0 で終わる。

**Why**: 無人で動かしても、壊れた版が居座らないようにする。再起動の瞬間は、Caddy が 502 を返す (数秒。個人用で許容)。

### R-7 e2 の定期実行

**Event**: 毎週月曜 12:00 (JST)。Dependabot (9:00) のあとで、自動マージとリリースが終わる時間を見込む
**System**: systemd タイマー (`feedgen-rs-update.timer`、`.service` は `Type=oneshot`)
**Response**: `update.sh` を実行する。結果は journal に残す。実行されなかった時間があれば、起動後に実行する (`Persistent=true`)。

### R-8 ログ・安全

- `update.sh` は、何をしたか (比較した版、置き換えた、戻した) を、標準出力に出す。journal で読める。
- 秘密情報 (トークンなど) を、ログとコマンドの引数に出さない。リポジトリを非公開にする場合の認証は、環境変数のファイル (`/etc/default/feedgen-rs-update`、モード 0600) から渡す。公開のままなら、認証は要らない。
- 取得先の URL は、`RELEASE_BASE_URL` (既定は `https://github.com/densuke/feedgen/releases`) で、テストのときだけ差し替える。
- `update.sh` を動かすユーザーは `densuke`。`sudo` は、`systemctl restart feedgen-rs.service` だけに限る (sudoers で、そのコマンドのみ許可する)。

## 4. 手動での戻し方

- 直前の版に戻す: `~/work/feedgen-rs/rollback-binary.sh` (`.prev` を戻して再起動し、`/health` を確かめる)。
- Python 版へ戻す: 既存の `rollback.sh` (Caddy の転送先を、`Caddyfile` のバックアップから戻す)。

## 5. テスト方針

- **`update.sh`** (壊れたときに、戻せる仕組みなので必須。実ネットワークを使わず、偽物で確かめる): ローカルの HTTP サーバー (127.0.0.1) に偽のリリースを置き、`systemctl` と `sudo` を偽物に差し替える。
  - 同じ版なら何もしない / 新しい版なら置き換える
  - チェックサムの不一致、不正なアーカイブ (`..`、余計なファイル) は、置き換えない
  - 起動後の `/health` が通らなければ、`.prev` に戻る
  - 取得の失敗は、終了コード 1 で、現行を壊さない
  - 途中で失敗しても、`VERSION` と実際のバイナリが食い違わない
- **ワークフロー**: `actionlint` で構文を検査する (手元で入っていれば)。実際の動作は、GitHub 上でしか確かめられない。確かめられない部分は、README に書く。
- **版の更新のロジック** (R-3): 版の計算は、小さなシェル関数にして、`tests/` で表のテストをする。

## 6. Python 版との差・既存への影響

- Python の Dockerfile、`compose.yml` は、今回は触らない (Rust 版の配布は、Docker を使わない)。
- 既存の Python 側のテストと CI は、存在しない (`.github` がない)。

## 7. 未決事項 (推奨つき)

- **D-R1** 配布物は、1 つの tar.gz に 2 つのバイナリをまとめる。推奨: この方針。サーバーのみを置くより、CLI も同じ版で揃う。
- **D-R2** 更新は、e2 のタイマーで週 1 回、自動で行う (ロールバックつき)。推奨: この方針。手動でも実行できる。
- **D-R3** リポジトリの公開範囲は、公開を前提に作る。非公開なら、R-8 の認証ファイルを足す。
- **D-R4** ワークフローは、main にマージされて初めて有効になる。推奨: このブランチの最後のコミットで足し、確認後に main へマージする。
- **D-R5** CI のカバレッジは、サマリのみで、しきい値を置かない。推奨: この方針 (開発の方針)。
