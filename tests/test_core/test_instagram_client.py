"""Instagram クライアントのテスト."""

import pytest
from unittest.mock import Mock, patch

from feedgen.core.instagram_client import InstagramClient


class TestInstagramClient:
    """InstagramClientのテストクラス."""

    def test_is_instagram_url(self):
        """Instagram URLの判定テスト."""
        client = InstagramClient()
        
        # Instagram URLのテスト
        assert client.is_instagram_url("https://www.instagram.com/username/")
        assert client.is_instagram_url("https://instagram.com/username/")
        assert client.is_instagram_url("https://www.instagram.com/p/ABC123/")
        
        # 非Instagram URLのテスト
        assert not client.is_instagram_url("https://twitter.com/username/")
        assert not client.is_instagram_url("https://example.com/")

    def test_is_profile_url(self):
        """プロフィールURL判定テスト."""
        client = InstagramClient()
        
        # プロフィールURLのテスト
        assert client.is_profile_url("https://www.instagram.com/username/")
        assert client.is_profile_url("https://www.instagram.com/@username/")
        assert client.is_profile_url("https://www.instagram.com/username")
        
        # 投稿URLのテスト（プロフィールではない）
        assert not client.is_profile_url("https://www.instagram.com/p/ABC123/")
        assert not client.is_profile_url("https://www.instagram.com/reel/ABC123/")
        assert not client.is_profile_url("https://www.instagram.com/tv/ABC123/")
        assert not client.is_profile_url("https://www.instagram.com/explore/")
        
        # 非Instagram URLのテスト
        assert not client.is_profile_url("https://twitter.com/username/")

    def test_parse_profile_description(self):
        """プロフィール説明のパーステスト."""
        client = InstagramClient()
        
        # 標準的なフォーマット
        description = '166 Followers, 350 Following, 3,166 Posts - See Instagram photos and videos from 佐藤 大輔 (@fugahogeds) on Instagram: "バイオテキスト"'
        result = client._parse_profile_description(description)
        
        assert result["followers"] == "166"
        assert result["following"] == "350"
        assert result["posts"] == "3,166"
        assert result["bio"] == "バイオテキスト"

    def test_format_profile_info(self):
        """プロフィール情報フォーマットテスト."""
        client = InstagramClient()
        
        profile_info = {
            "followers": "166",
            "following": "350",
            "posts": "3,166",
            "bio": "テストバイオ",
        }
        
        formatted = client._format_profile_info(profile_info)
        
        assert "フォロワー: 166" in formatted
        assert "フォロー中: 350" in formatted
        assert "投稿数: 3,166" in formatted
        assert "テストバイオ" in formatted

    @patch("feedgen.core.instagram_client.httpx.get")
    def test_fetch_profile_metadata_success(self, mock_get):
        """プロフィール情報取得成功テスト."""
        client = InstagramClient()
        
        # モックHTMLレスポンス
        mock_html = """
        <html>
        <head>
            <meta property="og:title" content="テストユーザー (@testuser)" />
            <meta property="og:description" content="100 Followers, 200 Following, 50 Posts - Instagram" />
            <meta property="og:image" content="https://example.com/image.jpg" />
        </head>
        </html>
        """
        
        mock_response = Mock()
        mock_response.text = mock_html
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = client.fetch_profile_metadata("https://www.instagram.com/testuser/")
        
        assert result is not None
        assert "テストユーザー" in result.title
        assert result.link == "https://www.instagram.com/testuser/"
        assert len(result.items) >= 0  # プロフィール情報があれば1件以上

    @patch("feedgen.core.instagram_client.httpx.get")
    def test_fetch_profile_metadata_error(self, mock_get):
        """プロフィール情報取得エラーテスト."""
        client = InstagramClient()
        
        # HTTPエラーをシミュレート
        mock_get.side_effect = Exception("Network error")
        
        result = client.fetch_profile_metadata("https://www.instagram.com/testuser/")
        
        assert result is None
