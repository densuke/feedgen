"""APIのエラー応答の仕様テスト.

仕様:
  - 内部アドレスのURLは 400 で拒否し、ネットワークへは出ない
  - 想定外の例外(500)は固定の文言を返し、例外の中身を漏らさない
  - 例外文に含まれる API キー(key=...)は伏せる
  - /feed は同期関数(スレッドプールで実行)にし、遅い取得でイベントループを止めない
"""

import inspect
from unittest.mock import patch

from fastapi.testclient import TestClient

from feedgen.api import main
from feedgen.core.exceptions import FeedGenerationError

client = TestClient(main.app, raise_server_exceptions=False)


class TestUnsafeUrl:
    def test_private_url_is_rejected_with_400(self):
        with patch("feedgen.core.safe_fetch._http_get") as get:
            response = client.get("/feed?url=http://127.0.0.1:9998/")
        assert response.status_code == 400
        get.assert_not_called()

    def test_metadata_url_is_rejected_with_400(self):
        with patch("feedgen.core.safe_fetch._http_get") as get:
            response = client.get("/feed?url=http://169.254.169.254/computeMetadata/v1/")
        assert response.status_code == 400
        get.assert_not_called()


class TestErrorBodies:
    @patch("feedgen.api.main.FeedGenerator")
    def test_internal_error_hides_exception_text(self, mock_generator_class):
        mock_generator_class.side_effect = RuntimeError("secret detail /home/densuke/x")
        response = client.get("/feed?url=https://example.com")
        assert response.status_code == 500
        assert "secret detail" not in response.text
        assert "/home/densuke" not in response.text

    @patch("feedgen.api.main.FeedGenerator")
    def test_api_key_in_error_text_is_redacted(self, mock_generator_class):
        generator = mock_generator_class.return_value
        generator.detect_existing_feeds.return_value = []
        generator.generate_feed.side_effect = FeedGenerationError(
            "YouTube API失敗 (<HttpError 403 when requesting "
            "https://www.googleapis.com/youtube/v3/search?key=AIzaSyFAKEKEY123&q=x returned>)"
        )
        response = client.get("/feed?url=https://example.com")
        assert response.status_code == 400
        assert "AIzaSyFAKEKEY123" not in response.text


class TestEndpointShape:
    def test_feed_endpoint_is_sync_function(self):
        assert not inspect.iscoroutinefunction(main.generate_feed)
