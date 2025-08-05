"""Google News URLデコーダーのテスト."""

from unittest.mock import patch

from feedgen.core.google_news_decoder import (
    GoogleNewsURLDecoder,
    GoogleNewsDecoderConfig,
)


class TestGoogleNewsURLDecoder:
    """GoogleNewsURLDecoderのテストクラス."""

    def test_init_default_values(self):
        """デフォルト値での初期化をテスト."""
        decoder = GoogleNewsURLDecoder()
        assert decoder.request_interval == 1
        assert decoder.request_timeout == 10
        assert decoder.max_retries == 3
        assert decoder.enable_logging is True

    def test_init_custom_values(self):
        """カスタム値での初期化をテスト."""
        decoder = GoogleNewsURLDecoder(
            request_interval=2,
            request_timeout=15,
            max_retries=5,
            enable_logging=False,
        )
        assert decoder.request_interval == 2
        assert decoder.request_timeout == 15
        assert decoder.max_retries == 5
        assert decoder.enable_logging is False

    def test_is_google_news_url_valid(self):
        """有効なGoogle News URLの判定をテスト."""
        decoder = GoogleNewsURLDecoder()
        
        valid_urls = [
            "https://news.google.com/articles/CBMiSWh0dHBzOi8vd3d3LnRva3lvLW5wLmNvLmpwL2FydGljbGUvNTUwMDYw0gEA",
            "https://news.google.com/articles/CBMi2AFBVV95cUxPd1ZCc1loODVVNHpnbFFTVHFkTG94?hl=ja&gl=JP&ceid=JP%3Aja",
        ]
        
        for url in valid_urls:
            assert decoder.is_google_news_url(url) is True

    def test_is_google_news_url_invalid(self):
        """無効なURLの判定をテスト."""
        decoder = GoogleNewsURLDecoder()
        
        invalid_urls = [
            "",
            "https://example.com",
            "https://news.google.com/topics/CAAqBwgKMKHL9QowkqbaAg",  # CBMiが含まれない
            "https://www.google.com/search?q=test",
            "https://news.yahoo.com/articles/123456",
        ]
        
        for url in invalid_urls:
            assert decoder.is_google_news_url(url) is False

    @patch('feedgen.core.google_news_decoder.gnewsdecoder')
    def test_decode_url_success(self, mock_gnewsdecoder):
        """URLデコード成功のテスト."""
        decoder = GoogleNewsURLDecoder()
        
        # モックの設定
        mock_gnewsdecoder.return_value = {
            "status": True,
            "decoded_url": "https://example.com/article/123"
        }
        
        google_news_url = "https://news.google.com/articles/CBMi123"
        result = decoder.decode_url(google_news_url)
        
        assert result == "https://example.com/article/123"
        mock_gnewsdecoder.assert_called_once_with(google_news_url, interval=1)

    @patch('feedgen.core.google_news_decoder.gnewsdecoder')
    def test_decode_url_failure(self, mock_gnewsdecoder):
        """URLデコード失敗のテスト."""
        decoder = GoogleNewsURLDecoder()
        
        # モックの設定（失敗）
        mock_gnewsdecoder.return_value = {
            "status": False,
            "message": "Decode failed"
        }
        
        google_news_url = "https://news.google.com/articles/CBMi123"
        result = decoder.decode_url(google_news_url)
        
        # 失敗時は元のURLを返す
        assert result == google_news_url

    @patch('feedgen.core.google_news_decoder.gnewsdecoder')
    def test_decode_url_string_response(self, mock_gnewsdecoder):
        """文字列レスポンスのテスト."""
        decoder = GoogleNewsURLDecoder()
        
        # モックの設定（直接文字列を返す場合）
        mock_gnewsdecoder.return_value = "https://example.com/article/123"
        
        google_news_url = "https://news.google.com/articles/CBMi123"
        result = decoder.decode_url(google_news_url)
        
        assert result == "https://example.com/article/123"

    def test_decode_url_non_google_news(self):
        """Google News以外のURLのテスト."""
        decoder = GoogleNewsURLDecoder()
        
        normal_url = "https://example.com/article/123"
        result = decoder.decode_url(normal_url)
        
        # Google News URLでない場合はそのまま返す
        assert result == normal_url

    @patch('feedgen.core.google_news_decoder.gnewsdecoder', None)
    def test_decode_url_library_not_available(self):
        """ライブラリが利用できない場合のテスト."""
        decoder = GoogleNewsURLDecoder()
        
        google_news_url = "https://news.google.com/articles/CBMi123"
        result = decoder.decode_url(google_news_url)
        
        # ライブラリが利用できない場合は元のURLを返す
        assert result == google_news_url

    @patch('feedgen.core.google_news_decoder.gnewsdecoder')
    def test_decode_urls_multiple(self, mock_gnewsdecoder):
        """複数URLの一括デコードテスト."""
        decoder = GoogleNewsURLDecoder(request_interval=0)  # テスト用に間隔を0に
        
        # モックの設定
        mock_gnewsdecoder.side_effect = [
            {"status": True, "decoded_url": "https://example.com/article/1"},
            {"status": True, "decoded_url": "https://example.com/article/2"},
        ]
        
        urls = [
            "https://news.google.com/articles/CBMi123",
            "https://news.google.com/articles/CBMi456",
        ]
        
        results = decoder.decode_urls(urls)
        
        assert len(results) == 2
        assert results[0] == "https://example.com/article/1"
        assert results[1] == "https://example.com/article/2"

    @patch('feedgen.core.google_news_decoder.gnewsdecoder')
    @patch('feedgen.core.google_news_decoder.time.sleep')
    def test_decode_url_with_retry(self, mock_sleep, mock_gnewsdecoder):
        """リトライ機能のテスト."""
        decoder = GoogleNewsURLDecoder(max_retries=2, request_interval=1)
        
        # 最初の2回は失敗、3回目で成功
        mock_gnewsdecoder.side_effect = [
            Exception("Network error"),
            Exception("Another error"),
            {"status": True, "decoded_url": "https://example.com/article/123"}
        ]
        
        google_news_url = "https://news.google.com/articles/CBMi123"
        result = decoder.decode_url(google_news_url)
        
        assert result == "https://example.com/article/123"
        assert mock_gnewsdecoder.call_count == 3
        # リトライ時のsleepが呼ばれることを確認（gnewsdecoderライブラリ内部でもsleepされる可能性があるため、最低2回）
        assert mock_sleep.call_count >= 2

    @patch('feedgen.core.google_news_decoder.gnewsdecoder')
    def test_decode_url_max_retries_exceeded(self, mock_gnewsdecoder):
        """最大リトライ回数超過のテスト."""
        decoder = GoogleNewsURLDecoder(max_retries=1)
        
        # 常に失敗
        mock_gnewsdecoder.side_effect = Exception("Network error")
        
        google_news_url = "https://news.google.com/articles/CBMi123"
        result = decoder.decode_url(google_news_url)
        
        # 失敗時は元のURLを返す
        assert result == google_news_url
        assert mock_gnewsdecoder.call_count == 2  # 初回 + 1回リトライ


class TestGoogleNewsDecoderConfig:
    """GoogleNewsDecoderConfigのテストクラス."""

    def test_init_default_values(self):
        """デフォルト値での初期化をテスト."""
        config = GoogleNewsDecoderConfig()
        assert config.decode_enabled is False
        assert config.request_interval == 1
        assert config.request_timeout == 10
        assert config.max_retries == 3
        assert config.enable_logging is True

    def test_init_custom_values(self):
        """カスタム値での初期化をテスト."""
        config = GoogleNewsDecoderConfig(
            decode_enabled=True,
            request_interval=2,
            request_timeout=15,
            max_retries=5,
            enable_logging=False,
        )
        assert config.decode_enabled is True
        assert config.request_interval == 2
        assert config.request_timeout == 15
        assert config.max_retries == 5
        assert config.enable_logging is False

    def test_from_dict(self):
        """辞書からの設定作成をテスト."""
        config_dict = {
            "decode_enabled": True,
            "request_interval": 3,
            "request_timeout": 20,
            "max_retries": 4,
            "enable_logging": False,
        }
        
        config = GoogleNewsDecoderConfig.from_dict(config_dict)
        
        assert config.decode_enabled is True
        assert config.request_interval == 3
        assert config.request_timeout == 20
        assert config.max_retries == 4
        assert config.enable_logging is False

    def test_from_dict_partial(self):
        """部分的な辞書からの設定作成をテスト."""
        config_dict = {
            "decode_enabled": True,
            "request_interval": 2,
        }
        
        config = GoogleNewsDecoderConfig.from_dict(config_dict)
        
        assert config.decode_enabled is True
        assert config.request_interval == 2
        assert config.request_timeout == 10  # デフォルト値
        assert config.max_retries == 3  # デフォルト値
        assert config.enable_logging is True  # デフォルト値

    def test_from_dict_empty(self):
        """空の辞書からの設定作成をテスト."""
        config = GoogleNewsDecoderConfig.from_dict({})
        
        # すべてデフォルト値
        assert config.decode_enabled is False
        assert config.request_interval == 1
        assert config.request_timeout == 10
        assert config.max_retries == 3
        assert config.enable_logging is True

    def test_create_decoder_enabled(self):
        """有効化されたデコーダーの作成をテスト."""
        config = GoogleNewsDecoderConfig(decode_enabled=True)
        decoder = config.create_decoder()
        
        assert decoder is not None
        assert isinstance(decoder, GoogleNewsURLDecoder)
        assert decoder.request_interval == 1
        assert decoder.request_timeout == 10
        assert decoder.max_retries == 3
        assert decoder.enable_logging is True

    def test_create_decoder_disabled(self):
        """無効化されたデコーダーの作成をテスト."""
        config = GoogleNewsDecoderConfig(decode_enabled=False)
        decoder = config.create_decoder()
        
        assert decoder is None

    def test_create_decoder_custom_values(self):
        """カスタム値でのデコーダー作成をテスト."""
        config = GoogleNewsDecoderConfig(
            decode_enabled=True,
            request_interval=2,
            request_timeout=15,
            max_retries=5,
            enable_logging=False,
        )
        decoder = config.create_decoder()
        
        assert decoder is not None
        assert decoder.request_interval == 2
        assert decoder.request_timeout == 15
        assert decoder.max_retries == 5
        assert decoder.enable_logging is False