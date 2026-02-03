"""翻訳キャッシュ機能実装."""

import hashlib
import logging
from abc import ABC, abstractmethod
from typing import Optional

try:
    import redis
except ImportError:
    redis = None

logger = logging.getLogger(__name__)


class TranslationCache(ABC):
    """翻訳キャッシュの抽象基底クラス."""

    @abstractmethod
    def get(self, text: str, target_lang: str) -> Optional[str]:
        """キャッシュから翻訳結果を取得.

        Args:
            text: 翻訳対象のテキスト
            target_lang: 翻訳先言語

        Returns:
            翻訳結果（キャッシュに存在しない場合はNone）
        """
        pass

    @abstractmethod
    def set(self, text: str, target_lang: str, translated: str, ttl: Optional[int] = None) -> None:
        """翻訳結果をキャッシュに保存.

        Args:
            text: 翻訳対象のテキスト
            target_lang: 翻訳先言語
            translated: 翻訳結果
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

    def _generate_cache_key(self, text: str, target_lang: str) -> str:
        """テキストと言語からキャッシュキーを生成.

        Args:
            text: 翻訳対象のテキスト
            target_lang: 翻訳先言語

        Returns:
            キャッシュキー
        """
        # テキストと言語を組み合わせてハッシュ化
        combined = f"{text}:{target_lang}"
        return hashlib.sha256(combined.encode('utf-8')).hexdigest()[:32]


class MemoryTranslationCache(TranslationCache):
    """インメモリ翻訳キャッシュ実装."""

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

        logger.info(f"Memory translation cache initialized: max_size={max_size}, default_ttl={default_ttl}")

    def get(self, text: str, target_lang: str) -> Optional[str]:
        """キャッシュから翻訳結果を取得."""
        cache_key = self._generate_cache_key(text, target_lang)

        try:
            if cache_key in self._cache:
                self._stats["hits"] += 1
                translated = self._cache[cache_key]
                logger.debug(f"Translation cache hit: {text[:50]}... -> {translated[:50]}...")
                return translated
            else:
                self._stats["misses"] += 1
                logger.debug(f"Translation cache miss: {text[:50]}...")
                return None
        except Exception as e:
            logger.warning(f"Error accessing memory translation cache: {e}")
            self._stats["misses"] += 1
            return None

    def set(self, text: str, target_lang: str, translated: str, ttl: Optional[int] = None) -> None:
        """翻訳結果をキャッシュに保存."""
        cache_key = self._generate_cache_key(text, target_lang)

        try:
            if ttl is not None and ttl != self.default_ttl:
                # TTLが異なる場合は個別設定が必要だが、cachetoolsの制限により
                # 全体のTTLを使用する
                logger.warning(f"Custom TTL {ttl} ignored, using default {self.default_ttl}")

            self._cache[cache_key] = translated
            self._stats["sets"] += 1
            logger.debug(f"Translation cache set: {text[:50]}... -> {translated[:50]}...")

        except Exception as e:
            logger.warning(f"Error setting memory translation cache: {e}")

    def clear(self) -> None:
        """キャッシュを全てクリア."""
        try:
            self._cache.clear()
            logger.info("Memory translation cache cleared")
        except Exception as e:
            logger.warning(f"Error clearing memory translation cache: {e}")

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
            logger.warning(f"Error getting memory translation cache stats: {e}")
            return {"error": str(e)}


class RedisTranslationCache(TranslationCache):
    """Redis翻訳キャッシュ実装."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        key_prefix: str = "feedgen:translation:",
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
            logger.info(f"Redis translation cache initialized: {redis_url}, prefix={key_prefix}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    def get(self, text: str, target_lang: str) -> Optional[str]:
        """キャッシュから翻訳結果を取得."""
        cache_key = self.key_prefix + self._generate_cache_key(text, target_lang)

        try:
            translated = self._redis.get(cache_key)
            if translated:
                self._stats["hits"] += 1
                logger.debug(f"Redis translation cache hit: {text[:50]}... -> {translated[:50]}...")
                return translated
            else:
                self._stats["misses"] += 1
                logger.debug(f"Redis translation cache miss: {text[:50]}...")
                return None
        except Exception as e:
            logger.warning(f"Error accessing Redis translation cache: {e}")
            self._stats["misses"] += 1
            return None

    def set(self, text: str, target_lang: str, translated: str, ttl: Optional[int] = None) -> None:
        """翻訳結果をキャッシュに保存."""
        cache_key = self.key_prefix + self._generate_cache_key(text, target_lang)
        ttl_to_use = ttl if ttl is not None else self.default_ttl

        try:
            self._redis.setex(cache_key, ttl_to_use, translated)
            self._stats["sets"] += 1
            logger.debug(f"Redis translation cache set: {text[:50]}... -> {translated[:50]}... (TTL: {ttl_to_use})")

        except Exception as e:
            logger.warning(f"Error setting Redis translation cache: {e}")

    def clear(self) -> None:
        """キャッシュを全てクリア（プレフィックス付きキーのみ）."""
        try:
            pattern = self.key_prefix + "*"
            keys = self._redis.keys(pattern)
            if keys:
                self._redis.delete(*keys)
                logger.info(f"Redis translation cache cleared: {len(keys)} keys removed")
            else:
                logger.info("Redis translation cache clear: no keys to remove")
        except Exception as e:
            logger.warning(f"Error clearing Redis translation cache: {e}")

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
            logger.warning(f"Error getting Redis translation cache stats: {e}")
            return {"error": str(e)}
