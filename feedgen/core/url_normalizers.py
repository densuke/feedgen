"""URL正規化システム."""

from abc import ABC, abstractmethod
from urllib.parse import urljoin, urlparse


class URLNormalizer(ABC):
    """URL正規化の基底クラス."""

    @abstractmethod
    def can_handle(self, base_url: str) -> bool:
        """このNormalizerがbase_URLを処理できるかを判定.
        
        Args:
            base_url: ベースURL
            
        Returns:
            処理可能な場合True
        """
        pass

    @abstractmethod
    def normalize(self, href: str, base_url: str) -> str:
        """URLを正規化.
        
        Args:
            href: 正規化対象のURL（相対URLの可能性あり）
            base_url: ベースURL
            
        Returns:
            正規化されたURL
        """
        pass


class DefaultURLNormalizer(URLNormalizer):
    """デフォルトのURL正規化クラス."""

    def can_handle(self, base_url: str) -> bool:
        """常にTrue（フォールバック用）."""
        return True

    def normalize(self, href: str, base_url: str) -> str:
        """標準的なURL正規化（既存ロジック）."""
        if href.startswith("http"):
            return href
        if href.startswith("/"):
            # ルート相対URLはホスト部分のみを使用
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}{href}"
        return base_url.rstrip("/") + "/" + href.lstrip("/")


class GoogleNewsURLNormalizer(URLNormalizer):
    """Google News専用のURL正規化クラス."""

    def __init__(self, decoder=None):
        """初期化.
        
        Args:
            decoder: Google News URLデコーダー（オプション）
        """
        self.decoder = decoder

    def can_handle(self, base_url: str) -> bool:
        """Google Newsのドメインかを判定."""
        parsed = urlparse(base_url)
        return parsed.netloc == "news.google.com"

    def normalize(self, href: str, base_url: str) -> str:
        """Google News用のURL正規化."""
        # 絶対URLの場合
        if href.startswith("http"):
            # Google News URLのデコードを試行
            if self.decoder and self.decoder.is_google_news_url(href):
                return self.decoder.decode_url(href)
            return href
            
        # Google News特有の相対URLパターンを処理
        if href.startswith("./articles/") or href.startswith("./read/"):
            # Google Newsのベースドメインと結合
            normalized_url = urljoin("https://news.google.com/", href[2:])  # "./"を除去
            # デコードを試行
            if self.decoder and self.decoder.is_google_news_url(normalized_url):
                return self.decoder.decode_url(normalized_url)
            return normalized_url
            
        # その他の相対URLは標準処理
        if href.startswith("/"):
            return "https://news.google.com" + href
            
        # 相対パスの場合はGoogle Newsのルートに結合
        return "https://news.google.com/" + href.lstrip("/")


class YouTubeURLNormalizer(URLNormalizer):
    """YouTube専用のURL正規化クラス."""

    def can_handle(self, base_url: str) -> bool:
        """YouTubeのドメインかを判定."""
        parsed = urlparse(base_url)
        return parsed.netloc == "www.youtube.com"

    def normalize(self, href: str, base_url: str) -> str:
        """YouTube用のURL正規化."""
        # 絶対URLはそのまま返す
        if href.startswith("http"):
            return href
            
        # YouTube特有の相対URLパターンを処理
        if href.startswith("/watch?v=") or href.startswith("/shorts/"):
            # YouTubeの動画URLは絶対URLに変換
            return "https://www.youtube.com" + href
            
        # チャンネルURL等の処理
        if href.startswith("/@") or href.startswith("/c/") or href.startswith("/channel/"):
            return "https://www.youtube.com" + href
            
        # その他の相対URLは標準処理
        if href.startswith("/"):
            return "https://www.youtube.com" + href
            
        # 相対パスの場合はYouTubeのルートに結合
        return "https://www.youtube.com/" + href.lstrip("/")


class URLNormalizerRegistry:
    """URL正規化クラスのレジストリ."""

    def __init__(self, google_news_decoder=None):
        """初期化.
        
        Args:
            google_news_decoder: Google News URLデコーダー（オプション）
        """
        self._normalizers: list[URLNormalizer] = []
        self._google_news_decoder = google_news_decoder
        self._setup_default_normalizers()

    def _setup_default_normalizers(self):
        """デフォルトのNormalizerを登録."""
        # 特定サイト用を先に登録（優先度が高い）
        self.register(GoogleNewsURLNormalizer(decoder=self._google_news_decoder))
        self.register(YouTubeURLNormalizer())
        # デフォルトは最後に登録（フォールバック）
        self.register(DefaultURLNormalizer())

    def register(self, normalizer: URLNormalizer):
        """Normalizerを登録.
        
        Args:
            normalizer: 登録するNormalizer
        """
        self._normalizers.append(normalizer)

    def normalize(self, href: str, base_url: str) -> str:
        """適切なNormalizerを使ってURLを正規化.
        
        Args:
            href: 正規化対象のURL
            base_url: ベースURL
            
        Returns:
            正規化されたURL
        """
        for normalizer in self._normalizers:
            if normalizer.can_handle(base_url):
                return normalizer.normalize(href, base_url)
        
        # フォールバック（通常は到達しない）
        return DefaultURLNormalizer().normalize(href, base_url)