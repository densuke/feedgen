"""Web API URL生成機能."""

from urllib.parse import urlencode, urlparse


class URLGenerator:
    """Web API URL生成クラス."""

    def __init__(self, api_base_url: str) -> None:
        """初期化.
        
        Args:
            api_base_url: Web APIのベースURL（例: https://example.com）
            
        """
        self.api_base_url = api_base_url.rstrip("/")

    def generate_feed_url(
        self,
        target_url: str,
        max_items: int | None = None,
        use_feed: bool | None = None,
        feed_first: bool | None = None,
        user_agent: str | None = None,
    ) -> str:
        """フィード取得用のAPI URLを生成.
        
        Args:
            target_url: 分析対象のURL
            max_items: 最大記事数
            use_feed: 既存フィード代理取得
            feed_first: フィード検出優先
            user_agent: User-Agentヘッダー
            
        Returns:
            生成されたAPI URL
            
        """
        # パラメータを準備
        params = {"url": target_url}
        
        if max_items is not None:
            params["max_items"] = str(max_items)
        
        if use_feed is not None:
            params["use_feed"] = "true" if use_feed else "false"
            
        if feed_first is not None:
            params["feed_first"] = "true" if feed_first else "false"
            
        if user_agent is not None:
            params["user_agent"] = user_agent
            
        # URL生成
        query_string = urlencode(params)
        return f"{self.api_base_url}/feed?{query_string}"

    def validate_base_url(self, base_url: str) -> bool:
        """ベースURLの妥当性をチェック.
        
        Args:
            base_url: チェック対象のベースURL
            
        Returns:
            URLが妥当かどうか
            
        """
        try:
            parsed = urlparse(base_url)
            return bool(parsed.scheme) and bool(parsed.netloc)
        except Exception:
            return False

    @staticmethod
    def normalize_base_url(base_url: str) -> str:
        """ベースURLを正規化.
        
        Args:
            base_url: 正規化対象のベースURL
            
        Returns:
            正規化されたベースURL
            
        """
        # プロトコルが無い場合はhttpsを追加
        if not base_url.startswith(("http://", "https://")):
            base_url = f"https://{base_url}"
            
        # 末尾のスラッシュを除去
        return base_url.rstrip("/")