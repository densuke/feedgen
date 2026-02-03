"""翻訳キャッシュのテスト."""

import pytest
from unittest.mock import MagicMock, patch

from feedgen.core.translation_cache import (
    TranslationCache,
    MemoryTranslationCache,
    RedisTranslationCache,
)


class TestMemoryTranslationCache:
    """MemoryTranslationCacheクラスのテスト."""

    def test_cache_can_be_instantiated(self):
        """キャッシュが初期化できる."""
        cache = MemoryTranslationCache()
        assert cache is not None

    def test_cache_get_miss_returns_none(self):
        """キャッシュミス時にNoneが返される."""
        cache = MemoryTranslationCache()
        result = cache.get("Hello, world!", "ja")
        assert result is None

    def test_cache_set_and_get(self):
        """キャッシュに保存して取得できる."""
        cache = MemoryTranslationCache()
        cache.set("Hello, world!", "ja", "こんにちは、世界！")

        result = cache.get("Hello, world!", "ja")
        assert result == "こんにちは、世界！"

    def test_cache_different_target_lang(self):
        """異なる翻訳先言語で別々にキャッシュされる."""
        cache = MemoryTranslationCache()
        cache.set("Hello", "ja", "こんにちは")
        cache.set("Hello", "ko", "안녕하세요")

        assert cache.get("Hello", "ja") == "こんにちは"
        assert cache.get("Hello", "ko") == "안녕하세요"

    def test_cache_clear(self):
        """キャッシュをクリアできる."""
        cache = MemoryTranslationCache()
        cache.set("Hello", "ja", "こんにちは")

        cache.clear()

        assert cache.get("Hello", "ja") is None

    def test_cache_get_stats(self):
        """キャッシュ統計情報を取得できる."""
        cache = MemoryTranslationCache()

        # 初期状態
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0

        # キャッシュミス
        cache.get("Hello", "ja")
        stats = cache.get_stats()
        assert stats["misses"] == 1

        # キャッシュセット
        cache.set("Hello", "ja", "こんにちは")
        stats = cache.get_stats()
        assert stats["size"] == 1

        # キャッシュヒット
        cache.get("Hello", "ja")
        stats = cache.get_stats()
        assert stats["hits"] == 1

    def test_cache_max_size(self):
        """最大サイズを超えると古いエントリが削除される."""
        cache = MemoryTranslationCache(max_size=2)

        cache.set("text1", "ja", "翻訳1")
        cache.set("text2", "ja", "翻訳2")
        cache.set("text3", "ja", "翻訳3")

        stats = cache.get_stats()
        assert stats["size"] <= 2


class TestRedisTranslationCache:
    """RedisTranslationCacheクラスのテスト."""

    @pytest.fixture
    def mock_redis(self):
        """Redisクライアントのモック."""
        with patch("feedgen.core.translation_cache.redis") as mock_redis_module:
            mock_client = MagicMock()
            mock_redis_module.from_url.return_value = mock_client
            yield mock_client

    def test_cache_can_be_instantiated(self, mock_redis):
        """キャッシュが初期化できる."""
        cache = RedisTranslationCache()
        assert cache is not None
        mock_redis.ping.assert_called_once()

    def test_cache_get_miss_returns_none(self, mock_redis):
        """キャッシュミス時にNoneが返される."""
        mock_redis.get.return_value = None

        cache = RedisTranslationCache()
        result = cache.get("Hello, world!", "ja")

        assert result is None
        mock_redis.get.assert_called_once()

    def test_cache_set_and_get(self, mock_redis):
        """キャッシュに保存して取得できる."""
        mock_redis.get.return_value = "こんにちは、世界！"

        cache = RedisTranslationCache()
        cache.set("Hello, world!", "ja", "こんにちは、世界！")
        result = cache.get("Hello, world!", "ja")

        assert result == "こんにちは、世界！"
        mock_redis.setex.assert_called_once()

    def test_cache_set_with_custom_ttl(self, mock_redis):
        """カスタムTTLでキャッシュに保存できる."""
        cache = RedisTranslationCache(default_ttl=3600)
        cache.set("Hello", "ja", "こんにちは", ttl=7200)

        # setexが7200秒のTTLで呼ばれることを確認
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 7200  # TTL引数

    def test_cache_clear(self, mock_redis):
        """キャッシュをクリアできる."""
        mock_redis.keys.return_value = ["key1", "key2"]

        cache = RedisTranslationCache(key_prefix="test:")
        cache.clear()

        mock_redis.keys.assert_called_once_with("test:*")
        mock_redis.delete.assert_called_once_with("key1", "key2")

    def test_cache_get_stats(self, mock_redis):
        """キャッシュ統計情報を取得できる."""
        mock_redis.keys.return_value = ["key1", "key2", "key3"]
        mock_redis.info.return_value = {
            "used_memory_human": "1.5M",
            "connected_clients": 5
        }

        cache = RedisTranslationCache()
        stats = cache.get_stats()

        assert "hits" in stats
        assert "misses" in stats
        assert "size" in stats
        assert stats["size"] == 3
        assert "redis_info" in stats

    def test_cache_connection_error(self):
        """Redis接続エラーが適切に処理される."""
        with patch("feedgen.core.translation_cache.redis") as mock_redis_module:
            mock_client = MagicMock()
            mock_client.ping.side_effect = Exception("Connection failed")
            mock_redis_module.from_url.return_value = mock_client

            with pytest.raises(Exception):
                RedisTranslationCache()
