"""Google Gemini APIを使用した翻訳機能."""

import logging
from typing import Optional

import google.generativeai as genai

from .models import RSSFeed, RSSItem
from .translation_cache import TranslationCache

logger = logging.getLogger(__name__)


class Translator:
    """Google Gemini APIを使用した翻訳クラス."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-flash",
        cache: Optional[TranslationCache] = None,
        target_lang: str = "ja",
        source_lang: str = "auto"
    ):
        """初期化.

        Args:
            api_key: Gemini API キー
            model: 使用するモデル名
            cache: 翻訳キャッシュ
            target_lang: 翻訳先言語
            source_lang: 翻訳元言語（"auto"で自動検出）
        """
        self.api_key = api_key
        self.model = model
        self.cache = cache
        self.target_lang = target_lang
        self.source_lang = source_lang

        # Gemini APIを設定
        genai.configure(api_key=api_key)
        self.model_instance = genai.GenerativeModel(model)

        logger.info(f"Translator initialized: model={model}, target_lang={target_lang}")

    def translate_text(self, text: str) -> str:
        """テキストを翻訳.

        Args:
            text: 翻訳対象のテキスト

        Returns:
            翻訳されたテキスト（失敗時は元のテキスト）
        """
        # 空文字列の場合はそのまま返す
        if not text or not text.strip():
            return text

        # キャッシュをチェック
        if self.cache:
            cached_translation = self.cache.get(text, self.target_lang)
            if cached_translation:
                logger.debug(f"Translation cache hit: {text[:50]}...")
                return cached_translation

        try:
            # 翻訳プロンプトを作成
            prompt = self._create_translation_prompt(text)

            # Gemini APIで翻訳
            response = self.model_instance.generate_content(prompt)
            translated = response.text.strip()

            # キャッシュに保存
            if self.cache:
                self.cache.set(text, self.target_lang, translated)

            logger.debug(f"Translated: {text[:50]}... -> {translated[:50]}...")
            return translated

        except Exception as e:
            logger.warning(f"Translation failed: {e}. Returning original text.")
            return text

    def translate_feed(self, feed: RSSFeed) -> RSSFeed:
        """フィード全体を翻訳.

        Args:
            feed: 翻訳対象のRSSFeed

        Returns:
            翻訳されたRSSFeed
        """
        # 各アイテムのタイトルと説明を翻訳
        translated_items = []
        for item in feed.items:
            translated_item = RSSItem(
                title=self.translate_text(item.title),
                description=self.translate_text(item.description),
                link=item.link,
                pub_date=item.pub_date,
                guid=item.guid
            )
            translated_items.append(translated_item)

        # 翻訳されたフィードを作成
        translated_feed = RSSFeed(
            title=feed.title,
            description=feed.description,
            link=feed.link,
            items=translated_items,
            last_build_date=feed.last_build_date
        )

        logger.info(f"Translated {len(translated_items)} items in feed")
        return translated_feed

    def _create_translation_prompt(self, text: str) -> str:
        """翻訳プロンプトを作成.

        Args:
            text: 翻訳対象のテキスト

        Returns:
            翻訳プロンプト
        """
        lang_names = {
            "ja": "日本語",
            "en": "英語",
            "ko": "韓国語",
            "zh": "中国語",
            "es": "スペイン語",
            "fr": "フランス語",
            "de": "ドイツ語",
        }

        target_lang_name = lang_names.get(self.target_lang, self.target_lang)

        if self.source_lang == "auto":
            prompt = f"以下のテキストを{target_lang_name}に翻訳してください。翻訳結果のみを出力し、説明や注釈は不要です。\n\n{text}"
        else:
            source_lang_name = lang_names.get(self.source_lang, self.source_lang)
            prompt = f"以下の{source_lang_name}のテキストを{target_lang_name}に翻訳してください。翻訳結果のみを出力し、説明や注釈は不要です。\n\n{text}"

        return prompt
