"""RSSフィード生成クラス."""

from datetime import datetime
from urllib.parse import urlparse

from .exceptions import FeedGenerationError, YouTubeAPIError
from .feed_detector import FeedDetector
from .models import RSSFeed
from .parser import HTMLParser
from .youtube_client import YouTubeAPIClient
from .google_news_decoder import GoogleNewsDecoderConfig


class FeedGenerator:
    """RSSフィード生成クラス."""

    def __init__(self, youtube_api_key: str | None = None, google_news_config: GoogleNewsDecoderConfig | None = None) -> None:
        """初期化.
        
        Args:
            youtube_api_key: YouTube Data API v3のAPIキー
            google_news_config: Google News設定
        """
        self.google_news_config = google_news_config
        self.parser = HTMLParser(google_news_config=google_news_config)
        self.feed_detector = FeedDetector()
        self.youtube_client = None
        self.instagram_client = None
        
        # YouTube APIキーが提供されている場合はクライアントを初期化
        if youtube_api_key:
            try:
                self.youtube_client = YouTubeAPIClient(api_key=youtube_api_key)
            except YouTubeAPIError:
                # APIキーが無効な場合はNoneのまま（フォールバック）
                self.youtube_client = None
        
        # Instagramクライアントを初期化
        from feedgen.core.instagram_client import InstagramClient
        self.instagram_client = InstagramClient()

    def detect_existing_feeds(self, url: str) -> list[dict]:
        """既存フィードを検出.
        
        Args:
            url: 検出対象のURL
            
        Returns:
            フィード情報のリスト
            
        Raises:
            FeedGenerationError: フィード検出に失敗した場合

        """
        return self.feed_detector.detect_feeds(url)

    def fetch_existing_feed(self, feed_url: str) -> tuple[str, str]:
        """既存フィードを取得.
        
        Args:
            feed_url: フィードのURL
            
        Returns:
            (フィード内容, Content-Type)のタプル
            
        Raises:
            FeedGenerationError: フィード取得に失敗した場合

        """
        return self.feed_detector.fetch_feed(feed_url)

    def generate_feed(self, url: str, config: dict | None = None) -> RSSFeed:
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

        # YouTube URLかどうかをチェック
        if self.youtube_client and self.youtube_client.can_handle_url(url):
            return self._generate_youtube_feed(url, max_items)
        
        # Instagram URLかどうかをチェック
        if self.instagram_client and self.instagram_client.is_instagram_url(url):
            return self._generate_instagram_feed(url, max_items)

        # Google News設定の更新（設定が変更されている場合）
        google_news_config_dict = config.get("google_news", {})
        if google_news_config_dict:
            google_news_config = GoogleNewsDecoderConfig.from_dict(google_news_config_dict)
            # 設定が変更されている場合はパーサーを再作成
            if google_news_config.decode_enabled != (self.google_news_config and self.google_news_config.decode_enabled):
                self.google_news_config = google_news_config
                self.parser = HTMLParser(user_agent=user_agent, google_news_config=google_news_config)
            else:
                # User-Agentのみ更新
                self.parser.user_agent = user_agent
        else:
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
                last_build_date=datetime.now(),
            )

            return feed

        except Exception as e:
            if isinstance(e, FeedGenerationError):
                raise
            raise FeedGenerationError(f"RSSフィード生成に失敗しました: {e}")

    def _generate_youtube_feed(self, url: str, max_items: int) -> RSSFeed:
        """YouTube検索URLからRSSフィードを生成.
        
        Args:
            url: YouTube検索URL
            max_items: 最大動画数
            
        Returns:
            生成されたRSSフィード
            
        Raises:
            FeedGenerationError: フィード生成に失敗した場合
        """
        try:
            # YouTube APIから動画データを取得
            items = self.youtube_client.get_feed_from_url(url, max_results=max_items)
            
            # 検索クエリから適切なタイトルを生成
            search_query = self.youtube_client.extract_search_query(url)
            
            # RSSフィードを生成
            feed = RSSFeed(
                title=f"YouTube検索: {search_query}",
                description=f"YouTube検索「{search_query}」の結果",
                link=url,
                items=items,
                last_build_date=datetime.now(),
            )
            
            return feed
            
        except YouTubeAPIError as e:
            # YouTube API失敗時はHTMLパーサーにフォールバック
            try:
                self.parser.user_agent = "feedgen/1.0"
                html_content = self.parser.fetch_content(url)
                metadata = self.parser.parse_metadata(html_content, url)
                items = self.parser.extract_articles(html_content, url, max_items)
                
                return RSSFeed(
                    title=metadata["title"],
                    description=metadata["description"],
                    link=metadata["link"],
                    items=items,
                    last_build_date=datetime.now(),
                )
            except Exception as fallback_error:
                raise FeedGenerationError(
                    f"YouTube API失敗 ({e}) およびフォールバック失敗 ({fallback_error})"
                )
        except Exception as e:
            raise FeedGenerationError(f"YouTube フィード生成に失敗しました: {e}")

    def _generate_instagram_feed(self, url: str, max_items: int = 20) -> RSSFeed:
        """Instagram URLからRSSフィードを生成.
        
        現在の軽量実装版ではプロフィール情報のみ取得可能。
        将来的な拡張: instaloaderを使用した投稿詳細の取得
        
        Args:
            url: Instagram URL
            max_items: 最大アイテム数（現在未使用）
            
        Returns:
            生成されたRSSフィード
            
        Raises:
            FeedGenerationError: フィード生成に失敗した場合
        """
        if not self.instagram_client:
            raise FeedGenerationError("Instagram クライアントが初期化されていません")
        
        # プロフィールURLでない場合はエラー
        if not self.instagram_client.is_profile_url(url):
            raise FeedGenerationError(
                "現在はInstagramプロフィールURLのみ対応しています。"
                "例: https://www.instagram.com/username/"
            )
        
        # プロフィール情報を取得
        feed_data = self.instagram_client.fetch_profile_metadata(url)
        
        if not feed_data:
            raise FeedGenerationError(f"Instagram プロフィール情報の取得に失敗しました: {url}")
        
        # RSSFeedに変換
        feed = RSSFeed(
            title=feed_data.title,
            description=feed_data.description,
            link=feed_data.link,
            items=feed_data.items,
            last_build_date=datetime.now(),
        )
        
        return feed
