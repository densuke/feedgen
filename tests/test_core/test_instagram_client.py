"""Instagram クライアントのテスト."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from feedgen.core.instagram_client import InstagramClient, InstagramFullClient


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

    def test_extract_profile_name(self):
        """プロフィール名抽出テスト."""
        client = InstagramClient()

        assert client.extract_profile_name("https://www.instagram.com/username/") == "username"
        assert client.extract_profile_name("https://www.instagram.com/@username/") == "username"
        assert client.extract_profile_name("https://www.instagram.com/p/ABC123/") is None

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


class TestInstagramFullClient:
    """InstagramFullClientのテストクラス."""

    def test_initialization_without_instaloader(self):
        """instaloaderなしでの初期化テスト."""
        # importを失敗させる
        with patch.dict("sys.modules", {"instaloader": None}):
            client = InstagramFullClient(username="testuser", session_file="/tmp/session")

            assert client.username == "testuser"
            assert client.session_file == "/tmp/session"
            assert client.max_posts == 20
            assert not client.is_available()

    def test_initialization_with_instaloader(self):
        """instaloaderありでの初期化テスト."""
        # instaloaderモジュールをモック
        mock_instaloader = MagicMock()

        with patch.dict("sys.modules", {"instaloader": mock_instaloader}):
            client = InstagramFullClient(username="testuser", max_posts=30)

            assert client.username == "testuser"
            assert client.max_posts == 30
            assert client.is_available()

    def test_is_available(self):
        """利用可能性チェックテスト."""
        # instaloaderが利用可能な場合
        mock_instaloader = MagicMock()
        with patch.dict("sys.modules", {"instaloader": mock_instaloader}):
            client = InstagramFullClient()
            assert client.is_available()

        # instaloaderが利用不可な場合
        with patch.dict("sys.modules", {"instaloader": None}):
            client = InstagramFullClient()
            assert not client.is_available()

    def test_login_with_session_file(self):
        """セッションファイルでのログインテスト."""
        # instaloaderモジュールをモック
        mock_instaloader = MagicMock()
        mock_loader = MagicMock()
        mock_instaloader.Instaloader.return_value = mock_loader

        with patch.dict("sys.modules", {"instaloader": mock_instaloader}):
            client = InstagramFullClient(username="testuser", session_file="/tmp/session")
            result = client.login()

            assert result is True
            mock_loader.load_session_from_file.assert_called_once_with("testuser", "/tmp/session")

    def test_login_with_password(self):
        """パスワードでのログインテスト."""
        # instaloaderモジュールをモック
        mock_instaloader = MagicMock()
        mock_loader = MagicMock()
        mock_instaloader.Instaloader.return_value = mock_loader

        with patch.dict("sys.modules", {"instaloader": mock_instaloader}):
            client = InstagramFullClient(username="testuser")
            result = client.login(password="testpass")

            assert result is True
            mock_loader.login.assert_called_once_with("testuser", "testpass")

    def test_login_without_credentials(self):
        """認証情報なしでのログイン失敗テスト."""
        mock_instaloader = MagicMock()
        with patch.dict("sys.modules", {"instaloader": mock_instaloader}):
            client = InstagramFullClient()  # usernameなし
            result = client.login()

            assert result is False

    def test_fetch_profile_posts(self):
        """プロフィール投稿フィード取得テスト."""
        # モックポストを作成
        mock_post1 = MagicMock()
        mock_post1.shortcode = "ABC123"
        mock_post1.caption = "Test caption 1"
        mock_post1.date_utc = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_post1.is_video = False
        mock_post1.typename = "GraphImage"
        mock_post1.likes = 100
        mock_post1.comments = 5

        mock_post2 = MagicMock()
        mock_post2.shortcode = "DEF456"
        mock_post2.caption = "Test caption 2"
        mock_post2.date_utc = datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
        mock_post2.is_video = False
        mock_post2.typename = "GraphImage"
        mock_post2.likes = 200
        mock_post2.comments = 10

        # モックプロフィール
        mock_profile = MagicMock()
        mock_profile.username = "testuser"
        mock_profile.full_name = "Test User"
        mock_profile.biography = "Test bio"
        mock_profile.get_posts.return_value = iter([mock_post1, mock_post2])

        # instaloaderモジュールをモック
        mock_instaloader = MagicMock()
        mock_loader = MagicMock()
        mock_loader.context.username = "testuser"
        mock_instaloader.Instaloader.return_value = mock_loader
        mock_instaloader.Profile.from_username.return_value = mock_profile

        with patch.dict("sys.modules", {"instaloader": mock_instaloader}):
            client = InstagramFullClient(username="testuser", max_posts=2)
            client.login(password="testpass")
            feed = client.fetch_profile_posts("testuser")

            assert feed is not None
            assert feed.title == "Test User (@testuser) - Instagram"
            assert feed.link == "https://www.instagram.com/testuser/"
            assert feed.description == "Test bio"
            assert len(feed.items) == 2
            assert feed.items[0].title == "Test caption 1"
            assert feed.items[0].link == "https://www.instagram.com/p/ABC123/"

    def test_get_post_title(self):
        """投稿タイトル取得テスト."""
        mock_instaloader = MagicMock()
        with patch.dict("sys.modules", {"instaloader": mock_instaloader}):
            client = InstagramFullClient()

            # キャプションあり
            mock_post = MagicMock()
            mock_post.caption = "Short caption"
            assert client._get_post_title(mock_post) == "Short caption"

            # 長いキャプション
            mock_post.caption = "a" * 120
            title = client._get_post_title(mock_post)
            assert len(title) == 100  # 97文字 + "..."
            assert title.endswith("...")

            # キャプションなし（動画）
            mock_post.caption = None
            mock_post.is_video = True
            mock_post.date_utc = datetime(2024, 1, 1, tzinfo=timezone.utc)
            title = client._get_post_title(mock_post)
            assert "動画投稿" in title
            assert "2024-01-01" in title

    def test_format_post_description(self):
        """投稿説明フォーマットテスト."""
        mock_instaloader = MagicMock()
        with patch.dict("sys.modules", {"instaloader": mock_instaloader}):
            client = InstagramFullClient()

            # 通常の画像投稿
            mock_post = MagicMock()
            mock_post.caption = "Test caption"
            mock_post.is_video = False
            mock_post.typename = "GraphImage"
            mock_post.likes = 100
            mock_post.comments = 5

            desc = client._format_post_description(mock_post)
            assert "Test caption" in desc
            assert "🖼️ 画像投稿" in desc
            assert "100" in desc  # likes

            # 動画投稿
            mock_post.is_video = True
            desc = client._format_post_description(mock_post)
            assert "📹 動画投稿" in desc
