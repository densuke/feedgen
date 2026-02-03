"""翻訳機能のテスト."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from feedgen.core.translator import Translator
from feedgen.core.translation_cache import MemoryTranslationCache
from feedgen.core.models import RSSFeed, RSSItem


class TestTranslator:
    """Translatorクラスのテスト."""

    @pytest.fixture
    def mock_genai(self):
        """Google Generative AIのモック."""
        with patch("feedgen.core.translator.genai") as mock:
            mock_model = MagicMock()
            mock.GenerativeModel.return_value = mock_model

            # generate_content()のモック
            mock_response = MagicMock()
            mock_response.text = "こんにちは、世界！"
            mock_model.generate_content.return_value = mock_response

            yield mock

    def test_translator_initialization(self, mock_genai):
        """Translatorが初期化できる."""
        translator = Translator(api_key="test-api-key")
        assert translator is not None
        mock_genai.configure.assert_called_once_with(api_key="test-api-key")

    def test_translate_text_success(self, mock_genai):
        """テキスト翻訳が成功する."""
        translator = Translator(api_key="test-api-key")
        result = translator.translate_text("Hello, world!")

        assert result == "こんにちは、世界！"
        # generate_contentが呼ばれたことを確認
        mock_genai.GenerativeModel.return_value.generate_content.assert_called_once()

    def test_translate_text_with_cache_miss(self, mock_genai):
        """キャッシュミス時にAPI呼び出しが行われる."""
        cache = MemoryTranslationCache()
        translator = Translator(api_key="test-api-key", cache=cache)

        result = translator.translate_text("Hello")

        assert result == "こんにちは、世界！"
        # キャッシュに保存されたことを確認
        cached = cache.get("Hello", "ja")
        assert cached == "こんにちは、世界！"

    def test_translate_text_with_cache_hit(self, mock_genai):
        """キャッシュヒット時にAPI呼び出しが行われない."""
        cache = MemoryTranslationCache()
        cache.set("Hello", "ja", "こんにちは（キャッシュ済み）")

        translator = Translator(api_key="test-api-key", cache=cache)
        result = translator.translate_text("Hello")

        assert result == "こんにちは（キャッシュ済み）"
        # API呼び出しが行われていないことを確認
        mock_genai.GenerativeModel.return_value.generate_content.assert_not_called()

    def test_translate_text_fallback_on_error(self, mock_genai):
        """API失敗時に元のテキストを返す."""
        mock_genai.GenerativeModel.return_value.generate_content.side_effect = Exception("API Error")

        translator = Translator(api_key="test-api-key")
        result = translator.translate_text("Hello, world!")

        # エラー時は元のテキストが返される
        assert result == "Hello, world!"

    def test_translate_text_with_custom_lang(self, mock_genai):
        """カスタム言語で翻訳できる."""
        mock_response = MagicMock()
        mock_response.text = "안녕하세요"
        mock_genai.GenerativeModel.return_value.generate_content.return_value = mock_response

        translator = Translator(api_key="test-api-key", target_lang="ko")
        result = translator.translate_text("Hello")

        assert result == "안녕하세요"

    def test_translate_feed(self, mock_genai):
        """フィード全体を翻訳できる."""
        # 複数の翻訳レスポンスを設定
        mock_responses = [
            MagicMock(text="翻訳されたタイトル1"),
            MagicMock(text="翻訳された説明1"),
            MagicMock(text="翻訳されたタイトル2"),
            MagicMock(text="翻訳された説明2"),
        ]
        mock_genai.GenerativeModel.return_value.generate_content.side_effect = mock_responses

        translator = Translator(api_key="test-api-key")

        # テスト用のフィード
        feed = RSSFeed(
            title="Test Feed",
            description="Test Description",
            link="https://example.com",
            items=[
                RSSItem(
                    title="Article 1",
                    description="Description 1",
                    link="https://example.com/1",
                    pub_date=datetime.now()
                ),
                RSSItem(
                    title="Article 2",
                    description="Description 2",
                    link="https://example.com/2",
                    pub_date=datetime.now()
                ),
            ]
        )

        translated_feed = translator.translate_feed(feed)

        # 記事のタイトルと説明が翻訳されていることを確認
        assert translated_feed.items[0].title == "翻訳されたタイトル1"
        assert translated_feed.items[0].description == "翻訳された説明1"
        assert translated_feed.items[1].title == "翻訳されたタイトル2"
        assert translated_feed.items[1].description == "翻訳された説明2"

        # リンクは変更されない
        assert translated_feed.items[0].link == "https://example.com/1"

    def test_translate_feed_with_empty_items(self, mock_genai):
        """アイテムが空のフィードでもエラーが発生しない."""
        translator = Translator(api_key="test-api-key")

        feed = RSSFeed(
            title="Empty Feed",
            description="No items",
            link="https://example.com",
            items=[]
        )

        translated_feed = translator.translate_feed(feed)
        assert len(translated_feed.items) == 0

    def test_translate_feed_partial_failure(self, mock_genai):
        """一部の翻訳が失敗しても処理が続行される."""
        # 1つ目は成功、2つ目は失敗
        mock_responses = [
            MagicMock(text="翻訳成功"),
            Exception("Translation failed"),
            MagicMock(text="Original title"),  # エラー時は元のテキスト
            MagicMock(text="Original description"),
        ]
        mock_genai.GenerativeModel.return_value.generate_content.side_effect = mock_responses

        translator = Translator(api_key="test-api-key")

        feed = RSSFeed(
            title="Test",
            description="Test",
            link="https://example.com",
            items=[
                RSSItem(
                    title="Original title",
                    description="Original description",
                    link="https://example.com/1"
                ),
            ]
        )

        translated_feed = translator.translate_feed(feed)

        # 翻訳が失敗した場合は元のテキストが保持される
        assert translated_feed.items[0].title == "Original title"
        assert translated_feed.items[0].description == "Original description"

    def test_translate_text_with_custom_model(self, mock_genai):
        """カスタムモデルを指定できる."""
        translator = Translator(api_key="test-api-key", model="gemini-1.5-pro")

        translator.translate_text("Hello")

        # カスタムモデルでGenerativeModelが呼ばれたことを確認
        mock_genai.GenerativeModel.assert_called_with("gemini-1.5-pro")

    def test_translate_empty_text(self, mock_genai):
        """空のテキストでもエラーが発生しない."""
        translator = Translator(api_key="test-api-key")
        result = translator.translate_text("")

        assert result == ""
        # 空文字列の場合はAPI呼び出しをスキップ
        mock_genai.GenerativeModel.return_value.generate_content.assert_not_called()

    def test_translate_text_strips_whitespace(self, mock_genai):
        """翻訳結果の前後の空白が削除される."""
        mock_response = MagicMock()
        mock_response.text = "  こんにちは  \n"
        mock_genai.GenerativeModel.return_value.generate_content.return_value = mock_response

        translator = Translator(api_key="test-api-key")
        result = translator.translate_text("Hello")

        assert result == "こんにちは"
