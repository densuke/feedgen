"""URL正規化システムのテスト."""

from unittest.mock import MagicMock

from feedgen.core.url_normalizers import (
    DefaultURLNormalizer,
    GoogleNewsURLNormalizer,
    URLNormalizerRegistry,
    YouTubeURLNormalizer,
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
        
    def setup_method_with_decoder(self):
        """デコーダー付きのテストメソッド実行前の準備."""
        self.mock_decoder = MagicMock()
        self.normalizer = GoogleNewsURLNormalizer(decoder=self.mock_decoder)

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

    def test_normalize_absolute_google_news_url_with_decoder(self):
        """絶対Google News URLのデコーダー付き正規化."""
        # デコーダー付きでセットアップ
        self.setup_method_with_decoder()
        
        # モックの設定
        google_news_url = "https://news.google.com/articles/CBMi123"
        decoded_url = "https://example.com/article/123"
        
        self.mock_decoder.is_google_news_url.return_value = True
        self.mock_decoder.decode_url.return_value = decoded_url
        
        base_url = "https://news.google.com/search?q=test"
        result = self.normalizer.normalize(google_news_url, base_url)
        
        # デコードが呼び出されて変換されたURLが返される
        assert result == decoded_url
        self.mock_decoder.is_google_news_url.assert_called_once_with(google_news_url)
        self.mock_decoder.decode_url.assert_called_once_with(google_news_url)

    def test_normalize_absolute_non_google_news_url_with_decoder(self):
        """絶対非Google News URLのデコーダー付き正規化."""
        self.setup_method_with_decoder()
        
        # モックの設定
        normal_url = "https://example.com/article"
        
        self.mock_decoder.is_google_news_url.return_value = False
        
        base_url = "https://news.google.com/search?q=test"
        result = self.normalizer.normalize(normal_url, base_url)
        
        # 通常のURLはそのまま返される
        assert result == normal_url
        self.mock_decoder.is_google_news_url.assert_called_once_with(normal_url)
        self.mock_decoder.decode_url.assert_not_called()

    def test_normalize_articles_url_with_decoder(self):
        """./articles/形式URLのデコーダー付き正規化."""
        self.setup_method_with_decoder()
        
        # モックの設定
        href = "./articles/CBMi123"
        expected_normalized = "https://news.google.com/articles/CBMi123"
        decoded_url = "https://example.com/article/123"
        
        self.mock_decoder.is_google_news_url.return_value = True
        self.mock_decoder.decode_url.return_value = decoded_url
        
        base_url = "https://news.google.com/search?q=test"
        result = self.normalizer.normalize(href, base_url)
        
        # 正規化後にデコードされる
        assert result == decoded_url
        self.mock_decoder.is_google_news_url.assert_called_once_with(expected_normalized)
        self.mock_decoder.decode_url.assert_called_once_with(expected_normalized)

    def test_normalize_without_decoder(self):
        """デコーダーなしでの正規化."""
        # デコーダーなしのnormalizerを使用
        href = "https://news.google.com/articles/CBMi123"
        base_url = "https://news.google.com/search?q=test"
        result = self.normalizer.normalize(href, base_url)
        
        # デコーダーがないのでそのまま返される
        assert result == href


class TestYouTubeURLNormalizer:
    """YouTubeURLNormalizerのテスト."""

    def setup_method(self):
        """テストメソッド実行前の準備."""
        self.normalizer = YouTubeURLNormalizer()

    def test_can_handle_youtube(self):
        """YouTubeのURLを処理できる."""
        assert self.normalizer.can_handle("https://www.youtube.com/results?search_query=test") is True
        assert self.normalizer.can_handle("https://www.youtube.com/watch?v=123") is True

    def test_can_handle_other_sites(self):
        """他のサイトは処理できない."""
        assert self.normalizer.can_handle("https://example.com") is False
        assert self.normalizer.can_handle("https://youtube.com") is False  # www.なし
        assert self.normalizer.can_handle("https://m.youtube.com") is False  # モバイル版

    def test_normalize_absolute_url(self):
        """絶対URLはそのまま返される."""
        href = "https://example.com/article"
        base_url = "https://www.youtube.com/results?search_query=test"
        result = self.normalizer.normalize(href, base_url)
        assert result == "https://example.com/article"

    def test_normalize_watch_url(self):
        """/watch?v=形式のURLの正規化."""
        href = "/watch?v=dQw4w9WgXcQ"
        base_url = "https://www.youtube.com/results?search_query=test"
        result = self.normalizer.normalize(href, base_url)
        assert result == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_normalize_shorts_url(self):
        """/shorts/形式のURLの正規化."""
        href = "/shorts/abc123def"
        base_url = "https://www.youtube.com/results?search_query=test"
        result = self.normalizer.normalize(href, base_url)
        assert result == "https://www.youtube.com/shorts/abc123def"

    def test_normalize_channel_urls(self):
        """チャンネルURL形式の正規化."""
        base_url = "https://www.youtube.com/results?search_query=test"
        
        test_cases = [
            ("/@channelname", "https://www.youtube.com/@channelname"),
            ("/c/ChannelName", "https://www.youtube.com/c/ChannelName"),
            ("/channel/UC123456789", "https://www.youtube.com/channel/UC123456789"),
        ]
        
        for href, expected in test_cases:
            result = self.normalizer.normalize(href, base_url)
            assert result == expected

    def test_normalize_root_relative_url(self):
        """ルート相対URL(/から始まる)の正規化."""
        href = "/playlist?list=PLrAXtmRdnEQy6nuLMfO2A8hwMHM9kFELH"
        base_url = "https://www.youtube.com/results?search_query=test"
        result = self.normalizer.normalize(href, base_url)
        assert result == "https://www.youtube.com/playlist?list=PLrAXtmRdnEQy6nuLMfO2A8hwMHM9kFELH"

    def test_normalize_other_relative_url(self):
        """その他の相対URLの正規化."""
        href = "some/path"
        base_url = "https://www.youtube.com/results?search_query=test"
        result = self.normalizer.normalize(href, base_url)
        assert result == "https://www.youtube.com/some/path"


class TestURLNormalizerRegistry:
    """URLNormalizerRegistryのテスト."""

    def setup_method(self):
        """テストメソッド実行前の準備."""
        self.registry = URLNormalizerRegistry()
        
    def setup_method_with_decoder(self):
        """デコーダー付きのテストメソッド実行前の準備."""
        self.mock_decoder = MagicMock()
        self.registry = URLNormalizerRegistry(google_news_decoder=self.mock_decoder)

    def test_google_news_normalization(self):
        """Google NewsのURLが正しく正規化される."""
        href = "./articles/CAIiEKTLBzuGJ_xNGjfO6HexHvwqGAgEKi4IAJSuHBAtjVT"
        base_url = "https://news.google.com/search?q=test"
        result = self.registry.normalize(href, base_url)
        assert result == "https://news.google.com/articles/CAIiEKTLBzuGJ_xNGjfO6HexHvwqGAgEKi4IAJSuHBAtjVT"

    def test_youtube_normalization(self):
        """YouTubeのURLが正しく正規化される."""
        href = "/watch?v=dQw4w9WgXcQ"
        base_url = "https://www.youtube.com/results?search_query=test"
        result = self.registry.normalize(href, base_url)
        assert result == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

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
        
        # YouTube
        base_url = "https://www.youtube.com/results?search_query=test"
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
        
        # YouTubeのURLでYouTube用の正規化が使用されることを確認
        href = "/watch?v=test123"
        base_url = "https://www.youtube.com/results?search_query=test"
        result = self.registry.normalize(href, base_url)
        # YouTube用の正規化が使用されるため、www.youtube.comドメインになる
        assert result == "https://www.youtube.com/watch?v=test123"

    def test_google_news_normalization_with_decoder(self):
        """デコーダー付きGoogle NewsのURLが正しく正規化される."""
        self.setup_method_with_decoder()
        
        # モックの設定
        href = "./articles/CBMi123"
        base_url = "https://news.google.com/search?q=test"
        expected_normalized = "https://news.google.com/articles/CBMi123"
        decoded_url = "https://example.com/article/123"
        
        self.mock_decoder.is_google_news_url.return_value = True
        self.mock_decoder.decode_url.return_value = decoded_url
        
        result = self.registry.normalize(href, base_url)
        
        # デコードされたURLが返される
        assert result == decoded_url
        self.mock_decoder.is_google_news_url.assert_called_once_with(expected_normalized)
        self.mock_decoder.decode_url.assert_called_once_with(expected_normalized)

    def test_registry_with_decoder_initialization(self):
        """デコーダー付きレジストリの初期化をテスト."""
        mock_decoder = MagicMock()
        registry = URLNormalizerRegistry(google_news_decoder=mock_decoder)
        
        # Google NewsのURLでデコーダーが使用されることを確認
        href = "https://news.google.com/articles/CBMi123"
        base_url = "https://news.google.com/search?q=test"
        
        mock_decoder.is_google_news_url.return_value = True
        mock_decoder.decode_url.return_value = "https://example.com/decoded"
        
        result = registry.normalize(href, base_url)
        
        assert result == "https://example.com/decoded"
        mock_decoder.is_google_news_url.assert_called_once_with(href)
        mock_decoder.decode_url.assert_called_once_with(href)