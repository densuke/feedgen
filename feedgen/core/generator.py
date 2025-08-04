"""RSSフィード生成クラス."""

from typing import Dict, Optional, Tuple, List
from datetime import datetime
from urllib.parse import urlparse
from .models import RSSFeed
from .parser import HTMLParser
from .feed_detector import FeedDetector
from .exceptions import FeedGenerationError


class FeedGenerator:
    """RSSフィード生成クラス."""
    
    def __init__(self) -> None:
        """初期化."""
        self.parser = HTMLParser()
        self.feed_detector = FeedDetector()
    
    def detect_existing_feeds(self, url: str) -> List[Dict]:
        """既存フィードを検出.
        
        Args:
            url: 検出対象のURL
            
        Returns:
            フィード情報のリスト
            
        Raises:
            FeedGenerationError: フィード検出に失敗した場合
        """
        return self.feed_detector.detect_feeds(url)
    
    def fetch_existing_feed(self, feed_url: str) -> Tuple[str, str]:
        """既存フィードを取得.
        
        Args:
            feed_url: フィードのURL
            
        Returns:
            (フィード内容, Content-Type)のタプル
            
        Raises:
            FeedGenerationError: フィード取得に失敗した場合
        """
        return self.feed_detector.fetch_feed(feed_url)
    
    def generate_feed(self, url: str, config: Optional[Dict] = None) -> RSSFeed:
        """指定されたURLからRSSフィードを生成.
        
        Args:
            url: 分析対象のURL
            config: 設定オプション
                - max_items: 最大記事数（デフォルト: 20）
                - cache_duration: キャッシュ有効時間（秒、デフォルト: 3600）
                - user_agent: User-Agentヘッダー
                
        Returns:
            生成されたRSSフィード
            
        Raises:
            FeedGenerationError: フィード生成に失敗した場合
        """
        if config is None:
            config = {}
        
        # 設定値の取得
        max_items = config.get("max_items", 20)
        user_agent = config.get("user_agent", "feedgen/1.0")
        
        # URLの妥当性チェック
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise FeedGenerationError(f"無効なURLです: {url}")
        
        # User-Agentを設定
        self.parser.user_agent = user_agent
        
        try:
            # HTMLコンテンツを取得
            html_content = self.parser.fetch_content(url)
            
            # メタデータを抽出
            metadata = self.parser.parse_metadata(html_content, url)
            
            # 記事一覧を抽出
            items = self.parser.extract_articles(html_content, url, max_items)
            
            # RSSフィードを生成
            feed = RSSFeed(
                title=metadata["title"],
                description=metadata["description"],
                link=metadata["link"],
                items=items,
                last_build_date=datetime.now()
            )
            
            return feed
            
        except Exception as e:
            if isinstance(e, FeedGenerationError):
                raise
            raise FeedGenerationError(f"RSSフィード生成に失敗しました: {e}")