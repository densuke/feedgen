"""URL正規化システムのテスト."""

import pytest

from feedgen.core.url_normalizers import (
    DefaultURLNormalizer,
    GoogleNewsURLNormalizer,
    URLNormalizerRegistry,
)


class TestDefaultURLNormalizer:
    """DefaultURLNormalizerのテスト."""

    def setup_method(self):
        """テストメソッド実行前の準備."""
        self.normalizer = DefaultURLNormalizer()

    def test_can_handle_returns_true(self):
        """can_handleは常にTrueを返す."""
        assert self.normalizer.can_handle("https://example.com") is True
        assert self.normalizer.can_handle("https://news.google.com") is True
        assert self.normalizer.can_handle("https://any-site.com") is True

    def test_normalize_absolute_url(self):
        """絶対URLはそのまま返される."""
        href = "https://example.com/article"
        base_url = "https://other.com"
        result = self.normalizer.normalize(href, base_url)
        assert result == "https://example.com/article"

    def test_normalize_root_relative_url(self):
        """ルート相対URLの正規化."""
        href = "/path/to/article"
        base_url = "https://example.com/some/page"
        result = self.normalizer.normalize(href, base_url)
        assert result == "https://example.com/path/to/article"

    def test_normalize_relative_url(self):
        """相対URLの正規化."""
        href = "article.html"
        base_url = "https://example.com/news"
        result = self.normalizer.normalize(href, base_url)
        assert result == "https://example.com/news/article.html"

    def test_normalize_relative_url_with_slash(self):
        """スラッシュ付き相対URLの正規化."""
        href = "subdir/article.html"
        base_url = "https://example.com/news/"
        result = self.normalizer.normalize(href, base_url)
        assert result == "https://example.com/news/subdir/article.html"


class TestGoogleNewsURLNormalizer:
    """GoogleNewsURLNormalizerのテスト."""

    def setup_method(self):
        """テストメソッド実行前の準備."""
        self.normalizer = GoogleNewsURLNormalizer()

    def test_can_handle_google_news(self):
        """Google NewsのURLを処理できる."""
        assert self.normalizer.can_handle("https://news.google.com/search?q=test") is True

    def test_can_handle_other_sites(self):
        """他のサイトは処理できない."""
        assert self.normalizer.can_handle("https://example.com") is False
        assert self.normalizer.can_handle("https://google.com") is False

    def test_normalize_absolute_url(self):
        """絶対URLはそのまま返される."""
        href = "https://example.com/article"
        base_url = "https://news.google.com/search?q=test"
        result = self.normalizer.normalize(href, base_url)
        assert result == "https://example.com/article"

    def test_normalize_articles_url(self):
        """./articles/形式のURLの正規化."""
        href = "./articles/CAIiEKTLBzuGJ_xNGjfO6HexHvwqGAgEKi4IAJSuHBAtjVT"
        base_url = "https://news.google.com/search?q=test"
        result = self.normalizer.normalize(href, base_url)
        assert result == "https://news.google.com/articles/CAIiEKTLBzuGJ_xNGjfO6HexHvwqGAgEKi4IAJSuHBAtjVT"

    def test_normalize_read_url(self):
        """./read/形式のURLの正規化."""
        href = "./read/CBMiQWh0dHBzOi8vd3d3LnNhbmtlaS5jb20vYXJ0aWNsZS8yMDI1"
        base_url = "https://news.google.com/search?q=test"
        result = self.normalizer.normalize(href, base_url)
        assert result == "https://news.google.com/read/CBMiQWh0dHBzOi8vd3d3LnNhbmtlaS5jb20vYXJ0aWNsZS8yMDI1"

    def test_normalize_root_relative_url(self):
        """ルート相対URL(/から始まる)の正規化."""
        href = "/topics/CAAqKggKIiRDQkFTRlFvSUwyMHZNRFZxYUdjU0JYcGhMVU5PSWdGRE1pZ0FQAQ"
        base_url = "https://news.google.com/search?q=test"
        result = self.normalizer.normalize(href, base_url)
        assert result == "https://news.google.com/topics/CAAqKggKIiRDQkFTRlFvSUwyMHZNRFZxYUdjU0JYcGhMVU5PSWdGRE1pZ0FQAQ"

    def test_normalize_other_relative_url(self):
        """その他の相対URLの正規化."""
        href = "some/path"
        base_url = "https://news.google.com/search?q=test"
        result = self.normalizer.normalize(href, base_url)
        assert result == "https://news.google.com/some/path"


class TestURLNormalizerRegistry:
    """URLNormalizerRegistryのテスト."""

    def setup_method(self):
        """テストメソッド実行前の準備."""
        self.registry = URLNormalizerRegistry()

    def test_google_news_normalization(self):
        """Google NewsのURLが正しく正規化される."""
        href = "./articles/CAIiEKTLBzuGJ_xNGjfO6HexHvwqGAgEKi4IAJSuHBAtjVT"
        base_url = "https://news.google.com/search?q=test"
        result = self.registry.normalize(href, base_url)
        assert result == "https://news.google.com/articles/CAIiEKTLBzuGJ_xNGjfO6HexHvwqGAgEKi4IAJSuHBAtjVT"

    def test_default_normalization(self):
        """一般的なサイトではデフォルトの正規化が使用される."""
        href = "/path/to/article"
        base_url = "https://example.com/news"
        result = self.registry.normalize(href, base_url)
        assert result == "https://example.com/path/to/article"

    def test_absolute_url_unchanged(self):
        """絶対URLはどのサイトでも変更されない."""
        href = "https://external.com/article"
        
        # Google News
        base_url = "https://news.google.com/search?q=test"
        result = self.registry.normalize(href, base_url)
        assert result == "https://external.com/article"
        
        # 一般サイト
        base_url = "https://example.com"
        result = self.registry.normalize(href, base_url)
        assert result == "https://external.com/article"

    def test_registry_priority(self):
        """レジストリの優先順序が正しく機能する."""
        # Google NewsのURLでGoogle News用の正規化が使用されることを確認
        href = "./articles/test"
        base_url = "https://news.google.com/search?q=test"
        result = self.registry.normalize(href, base_url)
        # Google News用の正規化が使用されるため、news.google.comドメインになる
        assert result.startswith("https://news.google.com/")
        assert "articles/test" in result