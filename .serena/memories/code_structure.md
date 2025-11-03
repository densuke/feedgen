## ディレクトリ構成
- `feedgen/core`: FeedGenerator、FeedDetector、HTMLParser、URL正規化、Google Newsデコーダー、Instagram/YouTubeクライアント、Pydanticモデル等。
- `feedgen/cli`: ClickベースのCLIエントリーポイントと設定ローダー、Web API起動ヘルパー。
- `feedgen/api`: FastAPIアプリ(`main.py`)でHTTPエンドポイントを提供。
- `tests`: core/cli/apiごとにpytestでユニット・統合テストを配置。
- `docs`: InstagramやYouTubeなどの追加設定ガイド。
- ルート: `pyproject.toml`(uv/依存定義), `config.example.yaml`, `Dockerfile`, `compose.yml`, `README.md`, `spec.md`, `task.md` 等。