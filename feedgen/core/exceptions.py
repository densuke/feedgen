"""feedgen のカスタム例外クラス."""


class FeedGenerationError(Exception):
    """RSSフィード生成時のエラー."""

    def __init__(self, message: str) -> None:
        """初期化.
        
        Args:
            message: エラーメッセージ

        """
        super().__init__(message)
        self.message = message


class ParseError(Exception):
    """HTML解析時のエラー."""

    def __init__(self, message: str) -> None:
        """初期化.
        
        Args:
            message: エラーメッセージ

        """
        super().__init__(message)
        self.message = message


class YouTubeAPIError(FeedGenerationError):
    """YouTube API関連のエラー."""
    pass


class InstagramAuthError(FeedGenerationError):
    """Instagram認証エラー."""
    pass


class InstagramRateLimitError(FeedGenerationError):
    """Instagramレート制限エラー."""
    pass
