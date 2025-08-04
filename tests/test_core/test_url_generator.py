"""URL生成機能のテスト."""

import pytest

from feedgen.core.url_generator import URLGenerator


class TestURLGenerator:
    """URLGeneratorクラスのテスト."""

    def test_url_generator_can_be_instantiated(self):
        """URLGeneratorクラスがインスタンス化できることをテスト."""
        generator = URLGenerator("https://example.com")
        assert generator.api_base_url == "https://example.com"

    def test_url_generator_strips_trailing_slash(self):
        """URLGeneratorが末尾のスラッシュを除去することをテスト."""
        generator = URLGenerator("https://example.com/")
        assert generator.api_base_url == "https://example.com"

    def test_generate_feed_url_basic(self):
        """基本的なフィードURL生成をテスト."""
        generator = URLGenerator("https://example.com")
        url = generator.generate_feed_url("https://target.com")
        
        assert url == "https://example.com/feed?url=https%3A%2F%2Ftarget.com"

    def test_generate_feed_url_with_all_params(self):
        """全パラメータを指定したフィードURL生成をテスト."""
        generator = URLGenerator("https://api.example.com")
        url = generator.generate_feed_url(
            target_url="https://target.com/blog",
            max_items=10,
            use_feed=True,
            feed_first=False,
            user_agent="custom-agent/1.0"
        )
        
        expected_params = [
            "url=https%3A%2F%2Ftarget.com%2Fblog",
            "max_items=10",
            "use_feed=true",
            "feed_first=false",
            "user_agent=custom-agent%2F1.0"
        ]
        
        assert url.startswith("https://api.example.com/feed?")
        for param in expected_params:
            assert param in url

    def test_generate_feed_url_with_partial_params(self):
        """一部のパラメータのみ指定したフィードURL生成をテスト."""
        generator = URLGenerator("https://feedgen.example.com")
        url = generator.generate_feed_url(
            target_url="https://blog.example.com",
            max_items=5,
            use_feed=True
        )
        
        assert "url=https%3A%2F%2Fblog.example.com" in url
        assert "max_items=5" in url
        assert "use_feed=true" in url
        assert "feed_first" not in url  # 指定されていないパラメータは含まれない
        assert "user_agent" not in url

    def test_generate_feed_url_boolean_false_values(self):
        """Falseの真偽値パラメータが正しく処理されることをテスト."""
        generator = URLGenerator("https://example.com")
        url = generator.generate_feed_url(
            target_url="https://target.com",
            use_feed=False,
            feed_first=False
        )
        
        assert "use_feed=false" in url
        assert "feed_first=false" in url

    def test_validate_base_url_valid_urls(self):
        """有効なベースURLの検証をテスト."""
        generator = URLGenerator("https://example.com")
        
        assert generator.validate_base_url("https://example.com") is True
        assert generator.validate_base_url("http://localhost:8000") is True
        assert generator.validate_base_url("https://api.feedgen.io") is True

    def test_validate_base_url_invalid_urls(self):
        """無効なベースURLの検証をテスト."""
        generator = URLGenerator("https://example.com")
        
        assert generator.validate_base_url("invalid-url") is False
        assert generator.validate_base_url("") is False
        assert generator.validate_base_url("ftp://example.com") is True  # スキームがあれば有効

    def test_normalize_base_url_adds_https(self):
        """normalize_base_urlがhttpsを追加することをテスト."""
        result = URLGenerator.normalize_base_url("example.com")
        assert result == "https://example.com"

    def test_normalize_base_url_preserves_http(self):
        """normalize_base_urlがhttpを保持することをテスト."""
        result = URLGenerator.normalize_base_url("http://example.com")
        assert result == "http://example.com"

    def test_normalize_base_url_preserves_https(self):
        """normalize_base_urlがhttpsを保持することをテスト."""
        result = URLGenerator.normalize_base_url("https://example.com")
        assert result == "https://example.com"

    def test_normalize_base_url_removes_trailing_slash(self):
        """normalize_base_urlが末尾のスラッシュを除去することをテスト."""
        result = URLGenerator.normalize_base_url("https://example.com/")
        assert result == "https://example.com"
        
        result = URLGenerator.normalize_base_url("example.com/")
        assert result == "https://example.com"

    def test_generate_feed_url_with_special_characters(self):
        """特殊文字を含むURLの生成をテスト."""
        generator = URLGenerator("https://example.com")
        url = generator.generate_feed_url(
            target_url="https://example.com/path?param=value&other=test",
            user_agent="my-bot/1.0 (+https://example.com/bot)"
        )
        
        # URLエンコーディングが正しく行われているかを確認
        assert "url=https%3A%2F%2Fexample.com%2Fpath%3Fparam%3Dvalue%26other%3Dtest" in url
        assert "user_agent=my-bot%2F1.0+%28%2Bhttps%3A%2F%2Fexample.com%2Fbot%29" in url

    def test_generate_feed_url_none_values_excluded(self):
        """None値のパラメータが除外されることをテスト."""
        generator = URLGenerator("https://example.com")
        url = generator.generate_feed_url(
            target_url="https://target.com",
            max_items=None,
            use_feed=None,
            feed_first=None,
            user_agent=None
        )
        
        # URLパラメータにはtarget_urlのみが含まれることを確認
        assert url == "https://example.com/feed?url=https%3A%2F%2Ftarget.com"