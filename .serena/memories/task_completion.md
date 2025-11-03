## タスク完了時チェックリスト
- `uv run pytest` で全テストが成功することを確認。
- `uv run ruff check .` でLintエラーが出ないことを確認。
- 仕様変更があれば `spec.md` や `README.md` を更新し、CLI/Web APIの使い方に齟齬がないか点検。
- 新しい設定項目を追加した場合は `config.example.yaml` と関連ドキュメントを更新。
- 大きな変更前後で `feedgen` CLI や `feedgen-serve` を実行し、主要ユースケースが動作するか手動確認。