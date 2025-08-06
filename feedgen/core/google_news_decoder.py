"""Google News URLデコード機能."""

import logging
import time
from typing import Optional
from urllib.parse import urlparse

try:
    from googlenewsdecoder import gnewsdecoder
except ImportError:
    gnewsdecoder = None

from .cache import URLDecodeCache, CacheConfig

logger = logging.getLogger(__name__)


class GoogleNewsURLDecoder:
    """Google News URLを実際の記事URLにデコードするクラス."""

    def __init__(
        self,
        request_interval: int = 1,
        request_timeout: int = 10,
        max_retries: int = 3,
        enable_logging: bool = True,
        cache: Optional[URLDecodeCache] = None,
    ):
        """初期化.
        
        Args:
            request_interval: リクエスト間隔（秒）
            request_timeout: タイムアウト（秒）
            max_retries: 最大リトライ回数
            enable_logging: ログ出力有効化
            cache: URLデコードキャッシュ
        """
        self.request_interval = request_interval
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.enable_logging = enable_logging
        self.cache = cache
        
        if gnewsdecoder is None:
            logger.error("googlenewsdecoder library is not installed")

    def is_google_news_url(self, url: str) -> bool:
        """Google News URLかどうかを判定.
        
        Args:
            url: 判定対象のURL
            
        Returns:
            Google News URLの場合True
        """
        if not url:
            return False
            
        parsed = urlparse(url)
        return (
            parsed.netloc == "news.google.com" and
            "/articles/" in parsed.path and
            "CBMi" in url
        )

    def decode_url(self, url: str) -> str:
        """Google News URLを実際の記事URLにデコード.
        
        Args:
            url: デコード対象のGoogle News URL
            
        Returns:
            デコードされたURL（失敗時は元のURL）
        """
        if not self.is_google_news_url(url):
            return url
            
        if gnewsdecoder is None:
            if self.enable_logging:
                logger.warning("googlenewsdecoder not available, returning original URL")
            return url

        # キャッシュからの取得を試行
        if self.cache:
            try:
                cached_result = self.cache.get(url)
                if cached_result:
                    if self.enable_logging:
                        logger.info(f"Cache hit for URL: {url[:100]}... -> {cached_result[:100]}...")
                    return cached_result
            except Exception as e:
                if self.enable_logging:
                    logger.warning(f"Cache get failed: {e}")

        # キャッシュミスまたはキャッシュ無効の場合はデコード実行
        for attempt in range(self.max_retries + 1):
            try:
                if self.enable_logging:
                    logger.info(f"Decoding Google News URL (attempt {attempt + 1}): {url[:100]}...")
                
                # リクエスト間隔制御
                if attempt > 0:
                    time.sleep(self.request_interval)
                
                result = gnewsdecoder(url, interval=self.request_interval)
                
                if isinstance(result, dict):
                    if result.get("status", False):
                        decoded_url = result.get("decoded_url", "")
                        if decoded_url and decoded_url != url:
                            if self.enable_logging:
                                logger.info(f"Successfully decoded URL: {decoded_url}")
                            
                            # キャッシュに保存
                            if self.cache:
                                try:
                                    self.cache.set(url, decoded_url)
                                except Exception as e:
                                    if self.enable_logging:
                                        logger.warning(f"Cache set failed: {e}")
                            
                            return decoded_url
                    else:
                        error_msg = result.get("message", "Unknown error")
                        if self.enable_logging:
                            logger.warning(f"Decode failed: {error_msg}")
                elif isinstance(result, str) and result != url:
                    # 直接文字列が返される場合
                    if self.enable_logging:
                        logger.info(f"Successfully decoded URL: {result}")
                    
                    # キャッシュに保存
                    if self.cache:
                        try:
                            self.cache.set(url, result)
                        except Exception as e:
                            if self.enable_logging:
                                logger.warning(f"Cache set failed: {e}")
                    
                    return result
                    
            except Exception as e:
                if self.enable_logging:
                    logger.warning(f"Decode attempt {attempt + 1} failed: {e}")
                if attempt == self.max_retries:
                    break
                time.sleep(self.request_interval)

        if self.enable_logging:
            logger.warning(f"Failed to decode URL after {self.max_retries + 1} attempts, returning original")
        return url

    def decode_urls(self, urls: list[str]) -> list[str]:
        """複数のURLを一括デコード.
        
        Args:
            urls: デコード対象のURLリスト
            
        Returns:
            デコードされたURLのリスト
        """
        decoded_urls = []
        for url in urls:
            decoded_url = self.decode_url(url)
            decoded_urls.append(decoded_url)
            
            # レート制限対応
            if url != decoded_url and self.request_interval > 0:
                time.sleep(self.request_interval)
                
        return decoded_urls


class GoogleNewsDecoderConfig:
    """Google News デコーダー設定クラス."""

    def __init__(
        self,
        decode_enabled: bool = False,
        request_interval: int = 1,
        request_timeout: int = 10,
        max_retries: int = 3,
        enable_logging: bool = True,
        cache_config: Optional[CacheConfig] = None,
    ):
        """初期化.
        
        Args:
            decode_enabled: デコード機能有効化
            request_interval: リクエスト間隔（秒）
            request_timeout: タイムアウト（秒）
            max_retries: 最大リトライ回数
            enable_logging: ログ出力有効化
            cache_config: キャッシュ設定
        """
        self.decode_enabled = decode_enabled
        self.request_interval = request_interval
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.enable_logging = enable_logging
        self.cache_config = cache_config or CacheConfig()

    @classmethod
    def from_dict(cls, config_dict: dict) -> "GoogleNewsDecoderConfig":
        """辞書から設定を作成.
        
        Args:
            config_dict: 設定辞書
            
        Returns:
            設定インスタンス
        """
        # キャッシュ設定を抽出
        cache_config = CacheConfig.from_dict(config_dict)
        
        return cls(
            decode_enabled=config_dict.get("decode_enabled", False),
            request_interval=config_dict.get("request_interval", 1),
            request_timeout=config_dict.get("request_timeout", 10),
            max_retries=config_dict.get("max_retries", 3),
            enable_logging=config_dict.get("enable_logging", True),
            cache_config=cache_config,
        )

    def create_decoder(self) -> Optional[GoogleNewsURLDecoder]:
        """デコーダーインスタンスを作成.
        
        Returns:
            デコーダーインスタンス（無効化されている場合はNone）
        """
        if not self.decode_enabled:
            return None
        
        # キャッシュインスタンスを作成
        cache = self.cache_config.create_cache()
        
        return GoogleNewsURLDecoder(
            request_interval=self.request_interval,
            request_timeout=self.request_timeout,
            max_retries=self.max_retries,
            enable_logging=self.enable_logging,
            cache=cache,
        )