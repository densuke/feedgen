"""フィード検出機能のテスト."""

import pytest
from unittest.mock import Mock, patch
from feedgen.core.feed_detector import FeedDetector
from feedgen.core.exceptions import FeedGenerationError


class TestFeedDetector:
    """フィード検出機能のテスト."""

    def test_detector_can_be_instantiated(self):
        """FeedDetectorクラスのインスタンスが作成できる."""
        detector = FeedDetector()
        assert detector is not None
        assert detector.user_agent == "feedgen/1.0"

    def test_detector_with_custom_user_agent(self):
        """カスタムUser-Agentでインスタンス作成できる."""
        detector = FeedDetector(user_agent="test-agent/2.0")
        assert detector.user_agent == "test-agent/2.0"

    @patch('feedgen.core.feed_detector.requests.get')
    def test_detect_from_html_rss_link(self, mock_get):
        """HTMLのRSSリンクタグからフィードを検出できる."""
        mock_response = Mock()
        mock_response.text = '''
        <html>
        <head>
            <link rel="alternate" type="application/rss+xml" title="RSS Feed" href="/feed.xml">
        </head>
        </html>
        '''
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        detector = FeedDetector()
        feeds = detector.detect_feeds("https://example.com")

        assert len(feeds) == 1
        assert feeds[0]['url'] == "https://example.com/feed.xml"
        assert feeds[0]['title'] == "RSS Feed"
        assert feeds[0]['type'] == "RSS"

    @patch('feedgen.core.feed_detector.requests.get')
    def test_detect_from_html_atom_link(self, mock_get):
        """HTMLのAtomリンクタグからフィードを検出できる."""
        mock_response = Mock()
        mock_response.text = '''
        <html>
        <head>
            <link rel="alternate" type="application/atom+xml" title="Atom Feed" href="/atom.xml">
        </head>
        </html>
        '''
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        detector = FeedDetector()
        feeds = detector.detect_feeds("https://example.com")

        assert len(feeds) == 1
        assert feeds[0]['url'] == "https://example.com/atom.xml"
        assert feeds[0]['title'] == "Atom Feed"
        assert feeds[0]['type'] == "Atom"

    @patch('feedgen.core.feed_detector.requests.head')
    @patch('feedgen.core.feed_detector.requests.get')
    def test_detect_from_common_paths(self, mock_get, mock_head):
        """一般的なフィードパスから検出できる."""
        # HTMLからは何も見つからない
        mock_get_response = Mock()
        mock_get_response.text = '<html><head></head></html>'
        mock_get_response.raise_for_status.return_value = None
        mock_get.return_value = mock_get_response

        # /feedパスでフィードが存在
        mock_head_response = Mock()
        mock_head_response.status_code = 200
        mock_head_response.headers = {'content-type': 'application/rss+xml'}
        mock_head.return_value = mock_head_response

        detector = FeedDetector()
        feeds = detector.detect_feeds("https://example.com")

        assert len(feeds) == 1
        assert feeds[0]['url'] == "https://example.com/feed"
        assert feeds[0]['type'] == "RSS"

    def test_is_feed_type(self):
        """Content-Typeがフィード形式かの判定."""
        detector = FeedDetector()
        
        assert detector._is_feed_type("application/rss+xml") == True
        assert detector._is_feed_type("application/atom+xml") == True
        assert detector._is_feed_type("application/xml") == True
        assert detector._is_feed_type("text/xml") == True
        assert detector._is_feed_type("application/json") == True
        assert detector._is_feed_type("text/html") == False

    def test_normalize_feed_type(self):
        """Content-Typeの正規化."""
        detector = FeedDetector()
        
        assert detector._normalize_feed_type("application/rss+xml") == "RSS"
        assert detector._normalize_feed_type("application/atom+xml") == "Atom" 
        assert detector._normalize_feed_type("application/json") == "JSON"
        assert detector._normalize_feed_type("application/xml") == "XML"

    def test_get_base_url(self):
        """ベースURLの取得."""
        detector = FeedDetector()
        
        assert detector._get_base_url("https://example.com/path/to/page") == "https://example.com"
        assert detector._get_base_url("http://test.org/feed") == "http://test.org"

    @patch('feedgen.core.feed_detector.requests.head')
    def test_check_feed_exists_true(self, mock_head):
        """フィードが存在する場合の確認."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'application/rss+xml'}
        mock_head.return_value = mock_response

        detector = FeedDetector()
        result = detector._check_feed_exists("https://example.com/feed")
        
        assert result == True

    @patch('feedgen.core.feed_detector.requests.head')
    def test_check_feed_exists_false(self, mock_head):
        """フィードが存在しない場合の確認."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_head.return_value = mock_response

        detector = FeedDetector()
        result = detector._check_feed_exists("https://example.com/feed")
        
        assert result == False

    def test_guess_feed_type_from_path(self):
        """パスからフィード形式を推測."""
        detector = FeedDetector()
        
        assert detector._guess_feed_type_from_path("/atom.xml") == "Atom"
        assert detector._guess_feed_type_from_path("/feed.json") == "JSON"
        assert detector._guess_feed_type_from_path("/rss") == "RSS"
        assert detector._guess_feed_type_from_path("/feed") == "RSS"

    @patch('feedgen.core.feed_detector.requests.get')
    def test_fetch_feed_success(self, mock_get):
        """フィード取得の成功."""
        mock_response = Mock()
        mock_response.text = '<?xml version="1.0"?><rss version="2.0"></rss>'
        mock_response.headers = {'content-type': 'application/rss+xml'}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        detector = FeedDetector()
        content, content_type = detector.fetch_feed("https://example.com/feed.xml")
        
        assert '<?xml version="1.0"?>' in content
        assert content_type == 'application/rss+xml'

    @patch('feedgen.core.feed_detector.requests.get')
    def test_fetch_feed_failure(self, mock_get):
        """フィード取得の失敗."""
        import requests
        mock_get.side_effect = requests.RequestException("Network error")

        detector = FeedDetector()
        
        with pytest.raises(FeedGenerationError):
            detector.fetch_feed("https://example.com/feed.xml")