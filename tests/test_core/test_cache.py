"""キャッシュ機能のテスト."""

import time
from unittest.mock import Mock, patch

from feedgen.core.cache import (
    MemoryURLDecodeCache,
    RedisURLDecodeCache,
    CacheConfig,
    URLDecodeCache,
)


class TestMemoryURLDecodeCache:
    """MemoryURLDecodeCacheのテストクラス."""

    def setup_method(self):
        """テストメソッド実行前の準備."""
        self.cache = MemoryURLDecodeCache(max_size=10, default_ttl=3600)

    def test_init_default_values(self):
        """デフォルト値での初期化をテスト."""
        cache = MemoryURLDecodeCache()
        assert cache.max_size == 1000
        assert cache.default_ttl == 86400

    def test_init_custom_values(self):
        """カスタム値での初期化をテスト."""
        cache = MemoryURLDecodeCache(max_size=500, default_ttl=3600)
        assert cache.max_size == 500
        assert cache.default_ttl == 3600

    def test_cache_key_generation(self):
        """キャッシュキー生成をテスト."""
        url1 = "https://news.google.com/articles/CBMi123"
        url2 = "https://news.google.com/articles/CBMi456"
        url3 = "https://news.google.com/articles/CBMi123"  # url1と同じ

        key1 = self.cache._generate_cache_key(url1)
        key2 = self.cache._generate_cache_key(url2)
        key3 = self.cache._generate_cache_key(url3)

        assert len(key1) == 32  # SHA256の前32文字
        assert key1 != key2  # 異なるURLは異なるキー
        assert key1 == key3  # 同じURLは同じキー
        assert isinstance(key1, str)

    def test_set_and_get_success(self):
        """キャッシュの保存と取得成功をテスト."""
        google_news_url = "https://news.google.com/articles/CBMi123"
        decoded_url = "https://example.com/article/123"

        # キャッシュに保存
        self.cache.set(google_news_url, decoded_url)

        # キャッシュから取得
        result = self.cache.get(google_news_url)
        assert result == decoded_url

    def test_get_cache_miss(self):
        """キャッシュミスをテスト."""
        google_news_url = "https://news.google.com/articles/CBMi123"
        result = self.cache.get(google_news_url)
        assert result is None

    def test_cache_stats(self):
        """キャッシュ統計情報をテスト."""
        google_news_url1 = "https://news.google.com/articles/CBMi123"
        google_news_url2 = "https://news.google.com/articles/CBMi456"
        decoded_url1 = "https://example.com/article/123"
        decoded_url2 = "https://example.com/article/456"

        # 初期統計
        stats = self.cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["sets"] == 0
        assert stats["size"] == 0

        # キャッシュミス
        self.cache.get("non-existent-url")
        stats = self.cache.get_stats()
        assert stats["misses"] == 1

        # キャッシュセット
        self.cache.set(google_news_url1, decoded_url1)
        stats = self.cache.get_stats()
        assert stats["sets"] == 1
        assert stats["size"] == 1

        # キャッシュヒット
        self.cache.get(google_news_url1)
        stats = self.cache.get_stats()
        assert stats["hits"] == 1

        # ヒット率計算
        assert stats["hit_rate"] == 0.5  # 1ヒット / (1ヒット + 1ミス)

    def test_clear_cache(self):
        """キャッシュクリアをテスト."""
        google_news_url = "https://news.google.com/articles/CBMi123"
        decoded_url = "https://example.com/article/123"

        # キャッシュに保存
        self.cache.set(google_news_url, decoded_url)
        assert self.cache.get(google_news_url) == decoded_url

        # キャッシュクリア
        self.cache.clear()

        # キャッシュが空になっていることを確認
        assert self.cache.get(google_news_url) is None
        stats = self.cache.get_stats()
        assert stats["size"] == 0

    def test_cache_size_limit(self):
        """キャッシュサイズ制限をテスト."""
        # 小さなキャッシュサイズで作成
        small_cache = MemoryURLDecodeCache(max_size=2, default_ttl=3600)

        # 制限を超えてアイテムを追加
        small_cache.set("url1", "decoded1")
        small_cache.set("url2", "decoded2")
        small_cache.set("url3", "decoded3")  # これで最初の要素が削除される

        # サイズが制限内であることを確認
        stats = small_cache.get_stats()
        assert stats["size"] <= 2


class TestRedisURLDecodeCache:
    """RedisURLDecodeCacheのテストクラス."""

    @patch('feedgen.core.cache.redis')
    def test_init_success(self, mock_redis_module):
        """Redis初期化成功をテスト."""
        mock_redis_client = Mock()
        mock_redis_client.ping.return_value = True
        mock_redis_module.from_url.return_value = mock_redis_client

        cache = RedisURLDecodeCache()
        assert cache.redis_url == "redis://localhost:6379/0"
        assert cache.key_prefix == "feedgen:gnews:"
        assert cache.default_ttl == 86400

        mock_redis_module.from_url.assert_called_once_with(
            "redis://localhost:6379/0", decode_responses=True
        )
        mock_redis_client.ping.assert_called_once()

    @patch('feedgen.core.cache.redis')
    def test_init_connection_failure(self, mock_redis_module):
        """Redis接続失敗をテスト."""
        mock_redis_module.from_url.side_effect = Exception("Connection failed")

        try:
            RedisURLDecodeCache()
            assert False, "Should raise exception"
        except Exception as e:
            assert "Connection failed" in str(e)

    @patch('feedgen.core.cache.redis')
    def test_set_and_get_success(self, mock_redis_module):
        """Redisキャッシュの保存と取得成功をテスト."""
        mock_redis_client = Mock()
        mock_redis_client.ping.return_value = True
        mock_redis_client.get.return_value = "https://example.com/article/123"
        mock_redis_module.from_url.return_value = mock_redis_client

        cache = RedisURLDecodeCache()
        google_news_url = "https://news.google.com/articles/CBMi123"
        decoded_url = "https://example.com/article/123"

        # キャッシュから取得
        result = cache.get(google_news_url)
        assert result == decoded_url

        # キャッシュに保存
        cache.set(google_news_url, decoded_url, ttl=7200)

        # 期待される呼び出しを確認
        expected_key = cache.key_prefix + cache._generate_cache_key(google_news_url)
        mock_redis_client.get.assert_called_with(expected_key)
        mock_redis_client.setex.assert_called_with(expected_key, 7200, decoded_url)

    @patch('feedgen.core.cache.redis')
    def test_get_cache_miss(self, mock_redis_module):
        """Redisキャッシュミスをテスト."""
        mock_redis_client = Mock()
        mock_redis_client.ping.return_value = True
        mock_redis_client.get.return_value = None
        mock_redis_module.from_url.return_value = mock_redis_client

        cache = RedisURLDecodeCache()
        google_news_url = "https://news.google.com/articles/CBMi123"

        result = cache.get(google_news_url)
        assert result is None

    @patch('feedgen.core.cache.redis')
    def test_clear_cache(self, mock_redis_module):
        """Redisキャッシュクリアをテスト."""
        mock_redis_client = Mock()
        mock_redis_client.ping.return_value = True
        mock_redis_client.keys.return_value = [
            "feedgen:gnews:key1",
            "feedgen:gnews:key2"
        ]
        mock_redis_module.from_url.return_value = mock_redis_client

        cache = RedisURLDecodeCache()
        cache.clear()

        # キー検索とクリアの呼び出しを確認
        mock_redis_client.keys.assert_called_with("feedgen:gnews:*")
        mock_redis_client.delete.assert_called_with(
            "feedgen:gnews:key1", "feedgen:gnews:key2"
        )

    @patch('feedgen.core.cache.redis')
    def test_get_stats(self, mock_redis_module):
        """Redis統計情報取得をテスト."""
        mock_redis_client = Mock()
        mock_redis_client.ping.return_value = True
        mock_redis_client.keys.return_value = ["key1", "key2"]
        mock_redis_client.info.return_value = {
            "used_memory_human": "1.5M",
            "connected_clients": 3
        }
        mock_redis_module.from_url.return_value = mock_redis_client

        cache = RedisURLDecodeCache()

        # キャッシュ操作して統計を蓄積
        cache.get("test-url")  # ミス
        cache.set("test-url", "decoded-url")  # セット

        stats = cache.get_stats()

        assert stats["hits"] == 0
        assert stats["misses"] == 1
        assert stats["sets"] == 1
        assert stats["size"] == 2
        assert stats["redis_info"]["used_memory"] == "1.5M"
        assert stats["redis_info"]["connected_clients"] == 3

    @patch('feedgen.core.cache.redis')
    def test_error_handling(self, mock_redis_module):
        """Redis操作エラーハンドリングをテスト."""
        mock_redis_client = Mock()
        mock_redis_client.ping.return_value = True
        mock_redis_client.get.side_effect = Exception("Redis error")
        mock_redis_client.setex.side_effect = Exception("Redis error")
        mock_redis_module.from_url.return_value = mock_redis_client

        cache = RedisURLDecodeCache()

        # エラーが発生してもNoneが返されることを確認
        result = cache.get("test-url")
        assert result is None

        # setでエラーが発生しても例外が伝播しないことを確認
        cache.set("test-url", "decoded-url")  # 例外が発生しない


class TestCacheConfig:
    """CacheConfigのテストクラス."""

    def test_init_default_values(self):
        """デフォルト値での初期化をテスト."""
        config = CacheConfig()
        assert config.enabled is True
        assert config.cache_type == "memory"
        assert config.ttl == 86400
        assert config.max_size == 1000
        assert config.redis_url == "redis://localhost:6379/0"
        assert config.redis_key_prefix == "feedgen:gnews:"

    def test_init_custom_values(self):
        """カスタム値での初期化をテスト."""
        config = CacheConfig(
            enabled=False,
            cache_type="redis",
            ttl=3600,
            max_size=500,
            redis_url="redis://localhost:6380/1",
            redis_key_prefix="test:"
        )
        assert config.enabled is False
        assert config.cache_type == "redis"
        assert config.ttl == 3600
        assert config.max_size == 500
        assert config.redis_url == "redis://localhost:6380/1"
        assert config.redis_key_prefix == "test:"

    def test_from_dict_complete(self):
        """完全な辞書からの設定作成をテスト."""
        config_dict = {
            "cache_enabled": True,
            "cache_type": "redis",
            "cache_ttl": 7200,
            "cache_max_size": 2000,
            "redis_url": "redis://test:6379/2",
            "redis_key_prefix": "myapp:"
        }

        config = CacheConfig.from_dict(config_dict)

        assert config.enabled is True
        assert config.cache_type == "redis"
        assert config.ttl == 7200
        assert config.max_size == 2000
        assert config.redis_url == "redis://test:6379/2"
        assert config.redis_key_prefix == "myapp:"

    def test_from_dict_partial(self):
        """部分的な辞書からの設定作成をテスト."""
        config_dict = {
            "cache_enabled": False,
            "cache_ttl": 1800,
        }

        config = CacheConfig.from_dict(config_dict)

        assert config.enabled is False
        assert config.ttl == 1800
        # デフォルト値が使用される
        assert config.cache_type == "memory"
        assert config.max_size == 1000

    def test_from_dict_empty(self):
        """空の辞書からの設定作成をテスト."""
        config = CacheConfig.from_dict({})

        # すべてデフォルト値
        assert config.enabled is True
        assert config.cache_type == "memory"
        assert config.ttl == 86400

    def test_create_cache_disabled(self):
        """キャッシュ無効時の作成をテスト."""
        config = CacheConfig(enabled=False)
        cache = config.create_cache()
        assert cache is None

    def test_create_cache_memory_enabled(self):
        """メモリキャッシュ有効時の作成をテスト."""
        config = CacheConfig(enabled=True, cache_type="memory")
        cache = config.create_cache()
        assert isinstance(cache, MemoryURLDecodeCache)
        assert cache.max_size == 1000
        assert cache.default_ttl == 86400

    @patch('feedgen.core.cache.redis')
    def test_create_cache_redis_enabled(self, mock_redis_module):
        """Redisキャッシュ有効時の作成をテスト."""
        mock_redis_client = Mock()
        mock_redis_client.ping.return_value = True
        mock_redis_module.from_url.return_value = mock_redis_client

        config = CacheConfig(
            enabled=True,
            cache_type="redis",
            redis_url="redis://test:6379/1"
        )
        cache = config.create_cache()
        assert isinstance(cache, RedisURLDecodeCache)
        assert cache.redis_url == "redis://test:6379/1"

    @patch('feedgen.core.cache.redis')
    def test_create_cache_redis_fallback_to_memory(self, mock_redis_module):
        """Redis失敗時のメモリキャッシュフォールバックをテスト."""
        mock_redis_module.from_url.side_effect = Exception("Redis connection failed")

        config = CacheConfig(enabled=True, cache_type="redis")
        cache = config.create_cache()

        # Redisに失敗してメモリキャッシュにフォールバックすること
        assert isinstance(cache, MemoryURLDecodeCache)

    @patch('feedgen.core.cache.MemoryURLDecodeCache')
    def test_create_cache_all_failed(self, mock_memory_cache):
        """全キャッシュ作成失敗をテスト."""
        mock_memory_cache.side_effect = Exception("Memory cache creation failed")

        config = CacheConfig(enabled=True, cache_type="memory")
        cache = config.create_cache()

        assert cache is None