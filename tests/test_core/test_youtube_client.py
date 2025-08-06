"""YouTubeAPIクライアントのテスト."""

import os
from unittest.mock import Mock, patch

import pytest

from feedgen.core.exceptions import YouTubeAPIError
from feedgen.core.youtube_client import YouTubeAPIClient


class TestYouTubeAPIClient:
    """YouTubeAPIClientのテスト."""

    def setup_method(self):
        """テストメソッド実行前の準備."""
        # テスト用のAPI Key
        self.test_api_key = "test_api_key_12345"

    def test_init_with_api_key(self):
        """APIキー指定での初期化テスト."""
        with patch('feedgen.core.youtube_client.build') as mock_build:
            mock_build.return_value = Mock()
            client = YouTubeAPIClient(api_key=self.test_api_key)
            assert client.api_key == self.test_api_key
            mock_build.assert_called_once_with("youtube", "v3", developerKey=self.test_api_key)

    def test_init_with_env_var(self):
        """環境変数からのAPI Key取得テスト."""
        with patch.dict(os.environ, {'YOUTUBE_API_KEY': self.test_api_key}):
            with patch('feedgen.core.youtube_client.build') as mock_build:
                mock_build.return_value = Mock()
                client = YouTubeAPIClient()
                assert client.api_key == self.test_api_key

    def test_init_without_api_key(self):
        """APIキー未設定時のエラーテスト."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(YouTubeAPIError, match="YouTube API Keyが設定されていません"):
                YouTubeAPIClient()

    def test_init_build_failure(self):
        """YouTube APIクライアント初期化失敗テスト."""
        with patch('feedgen.core.youtube_client.build') as mock_build:
            mock_build.side_effect = Exception("Build failed")
            with pytest.raises(YouTubeAPIError, match="YouTube APIクライアントの初期化に失敗しました"):
                YouTubeAPIClient(api_key=self.test_api_key)

    def test_can_handle_url_valid_youtube_search(self):
        """有効なYouTube検索URLの判定テスト."""
        with patch('feedgen.core.youtube_client.build'):
            client = YouTubeAPIClient(api_key=self.test_api_key)
            
            valid_urls = [
                "https://www.youtube.com/results?search_query=Python",
                "https://www.youtube.com/results?search_query=AI+%E9%96%8B%E7%99%BA&sp=CAESAA%253D%253D",
                "https://www.youtube.com/results?search_query=test&other_param=value",
            ]
            
            for url in valid_urls:
                assert client.can_handle_url(url) is True

    def test_can_handle_url_invalid(self):
        """無効なURLの判定テスト."""
        with patch('feedgen.core.youtube_client.build'):
            client = YouTubeAPIClient(api_key=self.test_api_key)
            
            invalid_urls = [
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "https://example.com/results?search_query=test",
                "https://www.youtube.com/channel/UC123456",
                "https://www.youtube.com/results",  # search_queryなし
                "https://google.com",
            ]
            
            for url in invalid_urls:
                assert client.can_handle_url(url) is False

    def test_extract_search_query_success(self):
        """検索クエリ抽出成功テスト."""
        with patch('feedgen.core.youtube_client.build'):
            client = YouTubeAPIClient(api_key=self.test_api_key)
            
            test_cases = [
                ("https://www.youtube.com/results?search_query=Python", "Python"),
                ("https://www.youtube.com/results?search_query=AI+%E9%96%8B%E7%99%BA", "AI 開発"),
                ("https://www.youtube.com/results?search_query=test&other=param", "test"),
            ]
            
            for url, expected in test_cases:
                result = client.extract_search_query(url)
                assert result == expected

    def test_extract_search_query_failure(self):
        """検索クエリ抽出失敗テスト."""
        with patch('feedgen.core.youtube_client.build'):
            client = YouTubeAPIClient(api_key=self.test_api_key)
            
            invalid_url = "https://www.youtube.com/results?other_param=value"
            with pytest.raises(YouTubeAPIError, match="検索クエリが見つかりません"):
                client.extract_search_query(invalid_url)

    def test_search_videos_success(self):
        """動画検索成功テスト."""
        with patch('feedgen.core.youtube_client.build') as mock_build:
            # モックレスポンスの設定
            mock_youtube = Mock()
            mock_search = Mock()
            mock_request = Mock()
            
            mock_build.return_value = mock_youtube
            mock_youtube.search.return_value = mock_search
            mock_search.list.return_value = mock_request
            
            # サンプルレスポンス
            mock_response = {
                "items": [
                    {
                        "id": {"videoId": "test_video_1"},
                        "snippet": {
                            "title": "テスト動画1",
                            "description": "テスト用の動画説明",
                            "channelTitle": "テストチャンネル",
                            "publishedAt": "2023-01-01T12:00:00Z"
                        }
                    },
                    {
                        "id": {"videoId": "test_video_2"},
                        "snippet": {
                            "title": "テスト動画2",
                            "description": "もう一つのテスト動画",
                            "channelTitle": "別のチャンネル",
                            "publishedAt": "2023-01-02T15:30:00Z"
                        }
                    }
                ]
            }
            mock_request.execute.return_value = mock_response
            
            client = YouTubeAPIClient(api_key=self.test_api_key)
            results = client.search_videos("Python", max_results=10)
            
            # 結果の検証
            assert len(results) == 2
            
            # 1つ目の動画
            assert results[0].title == "テスト動画1"
            assert results[0].link == "https://www.youtube.com/watch?v=test_video_1"
            assert "チャンネル: テストチャンネル" in results[0].description
            assert results[0].guid == "youtube-video-test_video_1"
            
            # 2つ目の動画
            assert results[1].title == "テスト動画2"
            assert results[1].link == "https://www.youtube.com/watch?v=test_video_2"
            assert "チャンネル: 別のチャンネル" in results[1].description

    def test_search_videos_no_youtube_client(self):
        """YouTubeクライアント未初期化エラーテスト."""
        with patch('feedgen.core.youtube_client.build'):
            client = YouTubeAPIClient(api_key=self.test_api_key)
            client.youtube = None  # 強制的にNoneに設定
            
            with pytest.raises(YouTubeAPIError, match="YouTube APIクライアントが初期化されていません"):
                client.search_videos("test")

    def test_search_videos_quota_exceeded(self):
        """クォータ超過エラーテスト."""
        with patch('feedgen.core.youtube_client.build') as mock_build:
            from googleapiclient.errors import HttpError
            
            mock_youtube = Mock()
            mock_build.return_value = mock_youtube
            
            # HttpErrorをモック
            error_content = b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}'
            http_error = HttpError(
                resp=Mock(status=403),
                content=error_content
            )
            http_error.error_details = [{"reason": "quotaExceeded"}]
            
            mock_youtube.search().list().execute.side_effect = http_error
            
            client = YouTubeAPIClient(api_key=self.test_api_key)
            
            with pytest.raises(YouTubeAPIError, match="YouTube APIのクォータを超過しました"):
                client.search_videos("test")

    def test_search_videos_invalid_key(self):
        """無効なAPIキーエラーテスト."""
        with patch('feedgen.core.youtube_client.build') as mock_build:
            from googleapiclient.errors import HttpError
            
            mock_youtube = Mock()
            mock_build.return_value = mock_youtube
            
            # HttpErrorをモック
            error_content = b'{"error": {"errors": [{"reason": "keyInvalid"}]}}'
            http_error = HttpError(
                resp=Mock(status=400),
                content=error_content
            )
            http_error.error_details = [{"reason": "keyInvalid"}]
            
            mock_youtube.search().list().execute.side_effect = http_error
            
            client = YouTubeAPIClient(api_key=self.test_api_key)
            
            with pytest.raises(YouTubeAPIError, match="YouTube APIキーが無効です"):
                client.search_videos("test")

    def test_search_videos_max_results_limit(self):
        """maxResults制限テスト."""
        with patch('feedgen.core.youtube_client.build') as mock_build:
            mock_youtube = Mock()
            mock_search = Mock()
            mock_request = Mock()
            
            mock_build.return_value = mock_youtube
            mock_youtube.search.return_value = mock_search
            mock_search.list.return_value = mock_request
            mock_request.execute.return_value = {"items": []}
            
            client = YouTubeAPIClient(api_key=self.test_api_key)
            
            # 範囲外の値をテスト
            client.search_videos("test", max_results=0)  # 最小値1に調整される
            mock_search.list.assert_called_with(
                part="snippet",
                q="test",
                type="video",
                maxResults=1,
                order="relevance"
            )
            
            client.search_videos("test", max_results=100)  # 最大値50に調整される
            mock_search.list.assert_called_with(
                part="snippet",
                q="test",
                type="video",
                maxResults=50,
                order="relevance"
            )

    def test_get_feed_from_url(self):
        """URLからフィード取得テスト."""
        with patch.object(YouTubeAPIClient, 'extract_search_query') as mock_extract:
            with patch.object(YouTubeAPIClient, 'search_videos') as mock_search:
                with patch('feedgen.core.youtube_client.build'):
                    
                    mock_extract.return_value = "Python"
                    mock_search.return_value = []
                    
                    client = YouTubeAPIClient(api_key=self.test_api_key)
                    url = "https://www.youtube.com/results?search_query=Python"
                    
                    client.get_feed_from_url(url, max_results=10)
                    
                    mock_extract.assert_called_once_with(url)
                    mock_search.assert_called_once_with("Python", 10)