## プロジェクト概要
- URLからRSS/Atomフィードを検出または生成するPython製ツール。
- コアライブラリ(feedgen.core)、CLI(feedgen.cli)、FastAPIベースのWeb API(feedgen.api)の三層構成。
- 主要依存: requests/httpx、BeautifulSoup4、feedgenerator、pydantic、click、FastAPI、uvicorn、google-api-python-client、cachetools。
- オプション機能: Google News URLデコード、YouTube検索フィード、Instagram軽量/フルクライアント対応。
- パッケージ/実行管理はuv(>=0.4)前提、Python 3.11+。