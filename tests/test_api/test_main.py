"""Web API テスト."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from feedgen.api.main import app
from feedgen.core.models import RSSFeed, RSSItem
from feedgen.core.exceptions import FeedGenerationError, ParseError

client = TestClient(app)


class TestRootEndpoint:
    """ルートエンドポイントのテスト."""
    
    def test_root_returns_api_info(self):
        """ルートエンドポイントがAPI情報を返すことをテスト."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["service"] == "feedgen API"
        assert data["version"] == "1.0.0"
        assert "endpoints" in data


class TestHealthEndpoint:
    """ヘルスチェックエンドポイントのテスト."""
    
    def test_health_check_returns_healthy(self):
        """ヘルスチェックが正常なレスポンスを返すことをテスト."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "healthy"
        assert data["service"] == "feedgen API"


class TestFeedEndpoint:
    """フィード生成エンドポイントのテスト."""
    
    def test_feed_endpoint_requires_url_parameter(self):
        """URLパラメータが必須であることをテスト."""
        response = client.get("/feed")
        
        assert response.status_code == 422  # Validation error
    
    @patch("feedgen.api.main.FeedGenerator")
    def test_feed_endpoint_basic_generation(self, mock_generator_class):
        """基本的なフィード生成をテスト."""
        # モックの設定
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        mock_generator.detect_existing_feeds.return_value = []
        
        # テスト用のRSSFeedを作成
        test_item = RSSItem(
            title="Test Article",
            description="Test description",
            link="https://example.com/article1",
            guid="test-1",
        )
        test_feed = RSSFeed(
            title="Test Feed",
            description="Test description",
            link="https://example.com",
            items=[test_item],
        )
        mock_generator.generate_feed.return_value = test_feed
        
        # APIを呼び出し
        response = client.get("/feed?url=https://example.com")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/rss+xml; charset=utf-8"
        assert "<?xml" in response.text
        assert "Test Feed" in response.text
    
    @patch("feedgen.api.main.FeedGenerator")
    def test_feed_endpoint_with_max_items(self, mock_generator_class):
        """max_itemsパラメータありでのフィード生成をテスト."""
        # モックの設定
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        mock_generator.detect_existing_feeds.return_value = []
        
        test_feed = RSSFeed(
            title="Test Feed",
            description="Test description", 
            link="https://example.com",
            items=[],
        )
        mock_generator.generate_feed.return_value = test_feed
        
        # APIを呼び出し
        response = client.get("/feed?url=https://example.com&max_items=10")
        
        assert response.status_code == 200
        # generate_feedが正しい設定で呼び出されているかを確認
        mock_generator.generate_feed.assert_called_once()
        call_args = mock_generator.generate_feed.call_args
        assert call_args[1]["config"]["max_items"] == 10
    
    @patch("feedgen.api.main.FeedGenerator")
    def test_feed_endpoint_use_feed_proxy(self, mock_generator_class):
        """use_feed=trueでの既存フィード代理取得をテスト."""
        # モックの設定
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        
        # 既存フィードが見つかる場合
        mock_generator.detect_existing_feeds.return_value = [{
            "url": "https://example.com/feed.xml",
            "title": "Existing Feed",
            "type": "RSS",
        }]
        mock_generator.fetch_existing_feed.return_value = (
            '<?xml version="1.0"?><rss><channel><title>Existing Feed</title></channel></rss>',
            "application/rss+xml"
        )
        
        # APIを呼び出し
        response = client.get("/feed?url=https://example.com&use_feed=true")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/rss+xml; charset=utf-8"
        assert "Existing Feed" in response.text
        
        # 代理取得メソッドが呼び出されていることを確認
        mock_generator.fetch_existing_feed.assert_called_once_with(
            "https://example.com/feed.xml"
        )
        # HTML解析は行われていないことを確認
        mock_generator.generate_feed.assert_not_called()
    
    @patch("feedgen.api.main.FeedGenerator")
    def test_feed_endpoint_feed_first_with_existing_feed(self, mock_generator_class):
        """feed_first=trueで既存フィードが見つかった場合をテスト."""
        # モックの設定
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        
        # 既存フィードが見つかる場合
        mock_generator.detect_existing_feeds.return_value = [{
            "url": "https://example.com/feed.xml",
            "title": "Existing Feed",
            "type": "RSS",
        }]
        
        test_feed = RSSFeed(
            title="Generated Feed",
            description="Generated description",
            link="https://example.com",
            items=[],
        )
        mock_generator.generate_feed.return_value = test_feed
        
        # APIを呼び出し
        response = client.get("/feed?url=https://example.com&feed_first=true")
        
        assert response.status_code == 200
        # 既存フィード情報がヘッダーに含まれることを確認
        assert "X-Existing-Feed-URL" in response.headers
        assert response.headers["X-Existing-Feed-URL"] == "https://example.com/feed.xml"
        assert response.headers["X-Existing-Feed-Title"] == "Existing Feed"
        assert response.headers["X-Existing-Feed-Type"] == "RSS"
        
        # HTML解析も実行されることを確認
        mock_generator.generate_feed.assert_called_once()
    
    @patch("feedgen.api.main.FeedGenerator")
    def test_feed_endpoint_handles_generation_error(self, mock_generator_class):
        """フィード生成エラーを適切にハンドリングすることをテスト."""
        # モックの設定
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        mock_generator.detect_existing_feeds.return_value = []
        mock_generator.generate_feed.side_effect = FeedGenerationError("Test error")
        
        # APIを呼び出し
        response = client.get("/feed?url=https://example.com")
        
        assert response.status_code == 400
        assert "Test error" in response.json()["detail"]
    
    @patch("feedgen.api.main.FeedGenerator")
    def test_feed_endpoint_handles_parse_error(self, mock_generator_class):
        """HTML解析エラーを適切にハンドリングすることをテスト."""
        # モックの設定
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        mock_generator.detect_existing_feeds.return_value = []
        mock_generator.generate_feed.side_effect = ParseError("Parse error")
        
        # APIを呼び出し
        response = client.get("/feed?url=https://example.com")
        
        assert response.status_code == 400
        assert "Parse error" in response.json()["detail"]
    
    @patch("feedgen.api.main.FeedGenerator")
    def test_feed_endpoint_handles_unexpected_error(self, mock_generator_class):
        """予期しないエラーを適切にハンドリングすることをテスト."""
        # モックの設定
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        mock_generator.detect_existing_feeds.side_effect = Exception("Unexpected error")
        
        # APIを呼び出し
        response = client.get("/feed?url=https://example.com")
        
        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]
    
    def test_feed_endpoint_validates_max_items_range(self):
        """max_itemsパラメータの範囲検証をテスト."""
        # 範囲外の値（負数）
        response = client.get("/feed?url=https://example.com&max_items=-1")
        assert response.status_code == 422
        
        # 範囲外の値（大きすぎる）
        response = client.get("/feed?url=https://example.com&max_items=101")
        assert response.status_code == 422
    
    @patch("feedgen.api.main.FeedGenerator")
    def test_feed_endpoint_with_user_agent(self, mock_generator_class):
        """user_agentパラメータの設定をテスト."""
        # モックの設定
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        mock_generator.detect_existing_feeds.return_value = []
        
        test_feed = RSSFeed(
            title="Test Feed",
            description="Test description",
            link="https://example.com",
            items=[],
        )
        mock_generator.generate_feed.return_value = test_feed
        
        # APIを呼び出し
        response = client.get("/feed?url=https://example.com&user_agent=custom-agent/1.0")
        
        assert response.status_code == 200
        
        # generate_feedが正しいuser_agentで呼び出されているかを確認
        call_args = mock_generator.generate_feed.call_args
        assert call_args[1]["config"]["user_agent"] == "custom-agent/1.0"


class TestAPIDocumentation:
    """API仕様ドキュメントのテスト."""
    
    def test_openapi_docs_accessible(self):
        """OpenAPI仕様書がアクセス可能であることをテスト."""
        response = client.get("/docs")
        assert response.status_code == 200
    
    def test_redoc_accessible(self):
        """ReDocがアクセス可能であることをテスト.""" 
        response = client.get("/redoc")
        assert response.status_code == 200
    
    def test_openapi_json_accessible(self):
        """OpenAPI JSONがアクセス可能であることをテスト."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        
        # JSON形式であることを確認
        openapi_spec = response.json()
        assert "openapi" in openapi_spec
        assert "info" in openapi_spec
        assert openapi_spec["info"]["title"] == "feedgen API"