"""FeedGeneratorクラスのテスト."""

import pytest
from feedgen.core import FeedGenerator, RSSFeed
from feedgen.core.exceptions import FeedGenerationError


class TestFeedGenerator:
    """FeedGeneratorクラスのテスト."""

    def test_feedgenerator_can_be_instantiated(self):
        """FeedGeneratorクラスのインスタンスが作成できる."""
        generator = FeedGenerator()
        assert generator is not None

    def test_generate_feed_with_valid_url(self):
        """有効なURLでRSSフィードが生成できる."""
        generator = FeedGenerator()
        url = "https://example.com"
        
        feed = generator.generate_feed(url)
        
        assert isinstance(feed, RSSFeed)
        assert feed.title is not None
        assert feed.description is not None
        assert feed.link is not None

    def test_generate_feed_with_config(self):
        """設定オプション付きでRSSフィードが生成できる."""
        generator = FeedGenerator()
        url = "https://example.com"
        config = {
            "max_items": 10,
            "cache_duration": 1800
        }
        
        feed = generator.generate_feed(url, config=config)
        
        assert isinstance(feed, RSSFeed)
        assert len(feed.items) <= 10

    def test_generate_feed_with_invalid_url_raises_error(self):
        """無効なURLでFeedGenerationErrorが発生する."""
        generator = FeedGenerator()
        invalid_url = "not-a-valid-url"
        
        with pytest.raises(FeedGenerationError):
            generator.generate_feed(invalid_url)

    def test_generate_feed_with_unreachable_url_raises_error(self):
        """アクセスできないURLでFeedGenerationErrorが発生する."""
        generator = FeedGenerator()
        unreachable_url = "https://nonexistent-domain-12345.com"
        
        with pytest.raises(FeedGenerationError):
            generator.generate_feed(unreachable_url)


class TestRSSFeed:
    """RSSFeedクラスのテスト."""

    def test_rssfeed_to_xml(self):
        """RSSFeedがXML文字列として出力できる."""
        # このテストは実装されたRSSFeedオブジェクトが必要
        pass  # 実装時に追加

    def test_rssfeed_to_dict(self):
        """RSSFeedが辞書形式として出力できる."""
        # このテストは実装されたRSSFeedオブジェクトが必要
        pass  # 実装時に追加