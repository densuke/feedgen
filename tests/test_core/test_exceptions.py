"""例外クラスのテスト."""

import pytest
from feedgen.core.exceptions import FeedGenerationError, ParseError


class TestExceptions:
    """例外クラスのテスト."""

    def test_feed_generation_error_can_be_raised(self):
        """FeedGenerationErrorが発生させられる."""
        with pytest.raises(FeedGenerationError):
            raise FeedGenerationError("テストエラー")

    def test_parse_error_can_be_raised(self):
        """ParseErrorが発生させられる."""
        with pytest.raises(ParseError):
            raise ParseError("パースエラー")

    def test_feed_generation_error_has_message(self):
        """FeedGenerationErrorにメッセージが含まれる."""
        message = "フィード生成に失敗しました"
        try:
            raise FeedGenerationError(message)
        except FeedGenerationError as e:
            assert str(e) == message

    def test_parse_error_has_message(self):
        """ParseErrorにメッセージが含まれる."""
        message = "HTML解析に失敗しました"
        try:
            raise ParseError(message)
        except ParseError as e:
            assert str(e) == message