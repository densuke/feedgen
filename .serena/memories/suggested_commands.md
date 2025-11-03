## よく使うコマンド
- `uv sync` : 依存関係の同期。
- `uv run feedgen https://example.com` : CLIでフィード生成。
- `uv run feedgen --use-feed URL` : 既存フィード代理取得モード。
- `uv run feedgen-serve --host 0.0.0.0 --port 8000` : FastAPIベースのWeb APIサーバーを起動。
- `uv run uvicorn feedgen.api.main:app --reload` : 開発用ホットリロードサーバー。
- `uv run pytest` : テストスイート実行。
- `uv run ruff check .` : Lintチェック。