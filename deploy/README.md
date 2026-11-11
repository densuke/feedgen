# 配備 (e2)

仕様は [docs/specs/release.md](../docs/specs/release.md)。

## 構成

| ファイル | 役割 |
|---|---|
| `update.sh` | 最新のタグ付きリリースを取得し、検証して置き換える。起動後の `/health` が通らなければ、自動で旧版に戻す |
| `rollback-binary.sh` | 直前の版 (`.prev`) に戻す |
| `lib.sh` | 上の 2 つの共通部分 (同じディレクトリに置く) |
| `next-patch.sh` | 版の patch を 1 つ上げる (リリースのワークフローが使う。e2 には不要) |
| `systemd/feedgen-rs-update.{service,timer}` | 週 1 回 (月曜 12:00 JST) に `update.sh` を実行する |
| `systemd/feedgen-rs-update.sudoers` | `feedgen-rs.service` の再起動だけを許す |
| `tests/` | 上のスクリプトのテスト (`bash deploy/tests/test_deploy.sh`) |

## e2 への導入

`~/work/feedgen-rs/` に `update.sh`、`lib.sh`、`rollback-binary.sh` を置く。

```bash
sudo visudo -cf deploy/systemd/feedgen-rs-update.sudoers
sudo install -m 0440 deploy/systemd/feedgen-rs-update.sudoers /etc/sudoers.d/feedgen-rs-update
sudo install -m 0644 deploy/systemd/feedgen-rs-update.service deploy/systemd/feedgen-rs-update.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now feedgen-rs-update.timer
```

### YouTube の検索 (任意)

YouTube の検索 URL を使うには、`feedgen-rs.service` に API キーを渡す。キーは、リポジトリ・ログ・チャットに出さない。

```bash
sudo install -m 0600 -o root -g root /dev/null /etc/default/feedgen-rs
sudoedit /etc/default/feedgen-rs        # YOUTUBE_API_KEY=<キー> の 1 行を書く
sudo systemctl edit feedgen-rs.service  # 下の 2 行を足す
#   [Service]
#   EnvironmentFile=-/etc/default/feedgen-rs
sudo systemctl daemon-reload
sudo systemctl restart feedgen-rs.service
```

キーがない間は、YouTube の検索 URL に 400 (`YouTube の検索には API キーの設定が必要です`) を返す。

## 運用

- すぐに更新を確認する: `sudo systemctl start feedgen-rs-update.service`
- 結果を見る: `journalctl -u feedgen-rs-update.service -n 50`
- 次の実行時刻: `systemctl list-timers feedgen-rs-update.timer`
- 自動更新を止める: `sudo systemctl disable --now feedgen-rs-update.timer`
- 直前の版に戻す: `~/work/feedgen-rs/rollback-binary.sh`
  (自動更新で戻したあとも、次回の実行で、同じ最新の版が再び入る。壊れた版を避けるときは、先にタイマーを止める)

## 注意

- 再起動の瞬間は、数秒、Caddy が 502 を返す。
- リポジトリが非公開の場合は、取得に認証が要る。`/etc/default/feedgen-rs-update` (モード 0600) で渡す設計にしてあるが、`update.sh` はまだ認証に対応していない。
- `update.sh` は、リリースが 1 つもない間は、「最新の版を解釈できません」で終了コード 1 になる (GitHub が `/releases/latest` を `/releases` へ転送するため。何も壊さない)。2026-11-03 に e2 で確認した。
- e2 の `~/work/feedgen-rs/VERSION` は、まだない (初回の手動配置のため)。最初のタグ付きリリースが出れば、`update.sh` が、それを入れて `VERSION` を作る。
