"""キャッシュ機能実装."""

import hashlib
import logging
import time
from abc import ABC, abstractmethod
from typing import Optional, Union
from urllib.parse import urlparse, unquote

try:
    import redis
except ImportError:
    redis = None

logger = logging.getLogger(__name__)


class URLDecodeCache(ABC):
    """URL デコードキャッシュの抽象基底クラス."""
    
    @abstractmethod
    def get(self, google_news_url: str) -> Optional[str]:
        """キャッシュからデコード済みURLを取得.
        
        Args:
            google_news_url: Google News URL
            
        Returns:
            デコード済みURL（キャッシュに存在しない場合はNone）
        """
        pass
    
    @abstractmethod
    def set(self, google_news_url: str, decoded_url: str, ttl: Optional[int] = None) -> None:
        """デコード済みURLをキャッシュに保存.
        
        Args:
            google_news_url: Google News URL
            decoded_url: デコード済みURL
            ttl: Time To Live（秒）
        """
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """キャッシュを全てクリア."""
        pass
    
    @abstractmethod
    def get_stats(self) -> dict:
        """キャッシュ統計情報を取得.
        
        Returns:
            統計情報（hits, misses, size等）
        """
        pass
    
    def _generate_cache_key(self, google_news_url: str) -> str:
        """Google News URLからキャッシュキーを生成.
        
        Args:
            google_news_url: Google News URL
            
        Returns:
            キャッシュキー
        """
        # URLを正規化してハッシュ化
        parsed = urlparse(google_news_url)
        normalized_url = f"{parsed.netloc}{parsed.path}"
        if parsed.query:
            normalized_url += f"?{parsed.query}"
        
        # SHA256でハッシュ化して短縮
        return hashlib.sha256(normalized_url.encode('utf-8')).hexdigest()[:32]


class MemoryURLDecodeCache(URLDecodeCache):
    """インメモリURL デコードキャッシュ実装."""
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 86400):
        """初期化.
        
        Args:
            max_size: 最大キャッシュサイズ
            default_ttl: デフォルトTTL（秒）
        """
        try:
            from cachetools import TTLCache
        except ImportError:
            raise ImportError("cachetools library is required for memory cache")
        
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache = TTLCache(maxsize=max_size, ttl=default_ttl)
        self._stats = {"hits": 0, "misses": 0, "sets": 0}
        
        logger.info(f"Memory cache initialized: max_size={max_size}, default_ttl={default_ttl}")
    
    def get(self, google_news_url: str) -> Optional[str]:
        """キャッシュからデコード済みURLを取得."""
        cache_key = self._generate_cache_key(google_news_url)
        
        try:
            if cache_key in self._cache:
                self._stats["hits"] += 1
                decoded_url = self._cache[cache_key]
                logger.debug(f"Cache hit: {google_news_url[:50]}... -> {decoded_url[:50]}...")
                return decoded_url
            else:
                self._stats["misses"] += 1
                logger.debug(f"Cache miss: {google_news_url[:50]}...")
                return None
        except Exception as e:
            logger.warning(f"Error accessing memory cache: {e}")
            self._stats["misses"] += 1
            return None
    
    def set(self, google_news_url: str, decoded_url: str, ttl: Optional[int] = None) -> None:
        """デコード済みURLをキャッシュに保存."""
        cache_key = self._generate_cache_key(google_news_url)
        
        try:
            if ttl is not None and ttl != self.default_ttl:
                # TTLが異なる場合は個別設定が必要だが、cachetoolsの制限により
                # 全体のTTLを使用する
                logger.warning(f"Custom TTL {ttl} ignored, using default {self.default_ttl}")
            
            self._cache[cache_key] = decoded_url
            self._stats["sets"] += 1
            logger.debug(f"Cache set: {google_news_url[:50]}... -> {decoded_url[:50]}...")
            
        except Exception as e:
            logger.warning(f"Error setting memory cache: {e}")
    
    def clear(self) -> None:
        """キャッシュを全てクリア."""
        try:
            self._cache.clear()
            logger.info("Memory cache cleared")
        except Exception as e:
            logger.warning(f"Error clearing memory cache: {e}")
    
    def get_stats(self) -> dict:
        """キャッシュ統計情報を取得."""
        try:
            return {
                **self._stats,
                "size": len(self._cache),
                "max_size": self.max_size,
                "hit_rate": self._stats["hits"] / max(self._stats["hits"] + self._stats["misses"], 1)
            }
        except Exception as e:
            logger.warning(f"Error getting memory cache stats: {e}")
            return {"error": str(e)}


class RedisURLDecodeCache(URLDecodeCache):
    """Redis URL デコードキャッシュ実装."""
    
    def __init__(
        self, 
        redis_url: str = "redis://localhost:6379/0",
        key_prefix: str = "feedgen:gnews:",
        default_ttl: int = 86400
    ):
        """初期化.
        
        Args:
            redis_url: Redis接続URL
            key_prefix: キープレフィックス
            default_ttl: デフォルトTTL（秒）
        """
        if redis is None:
            raise ImportError("redis library is required for Redis cache")
        
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl
        self._stats = {"hits": 0, "misses": 0, "sets": 0}
        
        try:
            self._redis = redis.from_url(redis_url, decode_responses=True)
            # 接続テスト
            self._redis.ping()
            logger.info(f"Redis cache initialized: {redis_url}, prefix={key_prefix}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    def get(self, google_news_url: str) -> Optional[str]:
        """キャッシュからデコード済みURLを取得."""
        cache_key = self.key_prefix + self._generate_cache_key(google_news_url)
        
        try:
            decoded_url = self._redis.get(cache_key)
            if decoded_url:
                self._stats["hits"] += 1
                logger.debug(f"Redis cache hit: {google_news_url[:50]}... -> {decoded_url[:50]}...")
                return decoded_url
            else:
                self._stats["misses"] += 1
                logger.debug(f"Redis cache miss: {google_news_url[:50]}...")
                return None
        except Exception as e:
            logger.warning(f"Error accessing Redis cache: {e}")
            self._stats["misses"] += 1
            return None
    
    def set(self, google_news_url: str, decoded_url: str, ttl: Optional[int] = None) -> None:
        """デコード済みURLをキャッシュに保存."""
        cache_key = self.key_prefix + self._generate_cache_key(google_news_url)
        ttl_to_use = ttl if ttl is not None else self.default_ttl
        
        try:
            self._redis.setex(cache_key, ttl_to_use, decoded_url)
            self._stats["sets"] += 1
            logger.debug(f"Redis cache set: {google_news_url[:50]}... -> {decoded_url[:50]}... (TTL: {ttl_to_use})")
            
        except Exception as e:
            logger.warning(f"Error setting Redis cache: {e}")
    
    def clear(self) -> None:
        """キャッシュを全てクリア（プレフィックス付きキーのみ）."""
        try:
            pattern = self.key_prefix + "*"
            keys = self._redis.keys(pattern)
            if keys:
                self._redis.delete(*keys)
                logger.info(f"Redis cache cleared: {len(keys)} keys removed")
            else:
                logger.info("Redis cache clear: no keys to remove")
        except Exception as e:
            logger.warning(f"Error clearing Redis cache: {e}")
    
    def get_stats(self) -> dict:
        """キャッシュ統計情報を取得."""
        try:
            # Redisから統計情報も取得
            pattern = self.key_prefix + "*"
            keys = self._redis.keys(pattern)
            size = len(keys)
            
            return {
                **self._stats,
                "size": size,
                "hit_rate": self._stats["hits"] / max(self._stats["hits"] + self._stats["misses"], 1),
                "redis_info": {
                    "used_memory": self._redis.info().get("used_memory_human", "unknown"),
                    "connected_clients": self._redis.info().get("connected_clients", 0)
                }
            }
        except Exception as e:
            logger.warning(f"Error getting Redis cache stats: {e}")
            return {"error": str(e)}


class CacheConfig:
    """キャッシュ設定クラス."""
    
    def __init__(
        self,
        enabled: bool = True,
        cache_type: str = "memory",
        ttl: int = 86400,
        max_size: int = 1000,
        redis_url: str = "redis://localhost:6379/0",
        redis_key_prefix: str = "feedgen:gnews:"
    ):
        """初期化.
        
        Args:
            enabled: キャッシュ有効化
            cache_type: キャッシュタイプ（'memory' or 'redis'）
            ttl: Time To Live（秒）
            max_size: メモリキャッシュ最大サイズ
            redis_url: Redis接続URL
            redis_key_prefix: Redisキープレフィックス
        """
        self.enabled = enabled
        self.cache_type = cache_type
        self.ttl = ttl
        self.max_size = max_size
        self.redis_url = redis_url
        self.redis_key_prefix = redis_key_prefix
    
    @classmethod
    def from_dict(cls, config_dict: dict) -> "CacheConfig":
        """辞書から設定を作成.
        
        Args:
            config_dict: 設定辞書
            
        Returns:
            設定インスタンス
        """
        return cls(
            enabled=config_dict.get("cache_enabled", True),
            cache_type=config_dict.get("cache_type", "memory"),
            ttl=config_dict.get("cache_ttl", 86400),
            max_size=config_dict.get("cache_max_size", 1000),
            redis_url=config_dict.get("redis_url", "redis://localhost:6379/0"),
            redis_key_prefix=config_dict.get("redis_key_prefix", "feedgen:gnews:")
        )
    
    def create_cache(self) -> Optional[URLDecodeCache]:
        """キャッシュインスタンスを作成.
        
        Returns:
            キャッシュインスタンス（無効化されている場合はNone）
        """
        if not self.enabled:
            return None
        
        try:
            if self.cache_type.lower() == "redis":
                return RedisURLDecodeCache(
                    redis_url=self.redis_url,
                    key_prefix=self.redis_key_prefix,
                    default_ttl=self.ttl
                )
            else:  # memory
                return MemoryURLDecodeCache(
                    max_size=self.max_size,
                    default_ttl=self.ttl
                )
        except Exception as e:
            logger.error(f"Failed to create {self.cache_type} cache: {e}")
            # フォールバックとしてメモリキャッシュを試行
            if self.cache_type.lower() != "memory":
                try:
                    logger.info("Falling back to memory cache")
                    return MemoryURLDecodeCache(
                        max_size=self.max_size,
                        default_ttl=self.ttl
                    )
                except Exception as fallback_e:
                    logger.error(f"Fallback to memory cache also failed: {fallback_e}")
            return None