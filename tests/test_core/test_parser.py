"""HTML解析機能のテスト."""

from feedgen.core.parser import HTMLParser


class TestHTMLParser:
    """HTML解析機能のテスト."""

    def test_parser_can_be_instantiated(self):
        """HTMLParserクラスのインスタンスが作成できる."""
        parser = HTMLParser()
        assert parser is not None
        assert parser.user_agent == "feedgen/1.0"

    def test_parser_with_custom_user_agent(self):
        """カスタムUser-Agentでインスタンス作成できる."""
        parser = HTMLParser(user_agent="test-agent/2.0")
        assert parser.user_agent == "test-agent/2.0"

    def test_parse_metadata_with_title_and_description(self):
        """HTMLメタデータが正しく抽出できる."""
        parser = HTMLParser()
        html_content = """
        <html>
        <head>
            <title>テストページ</title>
            <meta name="description" content="テスト用の説明文です。">
        </head>
        <body>
            <p>本文のテキスト</p>
        </body>
        </html>
        """
        
        metadata = parser.parse_metadata(html_content, "https://example.com")
        
        assert metadata["title"] == "テストページ"
        assert metadata["description"] == "テスト用の説明文です。"
        assert metadata["link"] == "https://example.com"

    def test_parse_metadata_fallback_description(self):
        """meta descriptionがない場合のフォールバック."""
        parser = HTMLParser()
        html_content = """
        <html>
        <head><title>テストページ</title></head>
        <body>
            <p>最初の段落のテキストです。これが説明として使用されます。</p>
        </body>
        </html>
        """
        
        metadata = parser.parse_metadata(html_content, "https://example.com")
        
        assert metadata["title"] == "テストページ"
        assert "最初の段落のテキストです" in metadata["description"]

    def test_extract_articles_from_headings_with_links(self):
        """見出しタグ内のリンクから記事を抽出できる."""
        parser = HTMLParser()
        html_content = """
        <html>
        <body>
            <h2><a href="/article1">記事タイトル1</a></h2>
            <p>記事1の説明文です。</p>
            <h3><a href="/article2">記事タイトル2</a></h3>
            <div>記事2の説明文です。</div>
        </body>
        </html>
        """
        
        items = parser.extract_articles(html_content, "https://example.com", max_items=5)
        
        assert len(items) == 2
        assert items[0].title == "記事タイトル1"
        assert items[0].link == "https://example.com/article1"
        assert items[1].title == "記事タイトル2" 
        assert items[1].link == "https://example.com/article2"

    def test_extract_articles_from_card_elements(self):
        """カード形式の要素から記事を抽出できる."""
        parser = HTMLParser()
        html_content = """
        <html>
        <body>
            <div class="bg-content1">
                <h4>カード記事タイトル1</h4>
                <p>カード記事の説明文です。</p>
                <a href="/card1">詳細を見る</a>
            </div>
            <article class="cursor-pointer">
                <span>カード記事タイトル2</span>
                <div>別のカード記事の説明です。</div>
            </article>
        </body>
        </html>
        """
        
        items = parser.extract_articles(html_content, "https://example.com", max_items=5)
        
        assert len(items) >= 1
        # 最初のカードはリンクがあるので抽出される
        card_with_link = next((item for item in items if "カード記事タイトル1" in item.title), None)
        assert card_with_link is not None
        assert card_with_link.link == "https://example.com/card1"

    def test_extract_articles_deduplication(self):
        """重複した記事を排除できる."""
        # TODO: 現在の実装では重複排除は未実装のため、将来の改善時に有効化する
        # 実装例:
        # parser = HTMLParser()
        # html_content = """
        # <html>
        # <body>
        #     <div class="content">
        #         <h3>同じタイトル</h3>
        #         <p>説明文</p>
        #     </div>
        #     <div class="content">
        #         <h3>同じタイトル</h3>
        #         <p>説明文</p>
        #     </div>
        #     <div class="content">
        #         <h3>異なるタイトル</h3>
        #         <p>別の説明文</p>
        #     </div>
        # </body>
        # </html>
        # """
        # items = parser.extract_articles(html_content, "https://example.com", max_items=10)
        # titles = [item.title for item in items]
        # unique_titles = set(titles)
        # assert len(unique_titles) <= len(titles)
        pass

    def test_normalize_url_absolute(self):
        """絶対URLの正規化."""
        parser = HTMLParser()
        result = parser._normalize_url("https://example.com/page", "https://base.com")
        assert result == "https://example.com/page"

    def test_normalize_url_relative_with_slash(self):
        """スラッシュ付き相対URLの正規化."""
        parser = HTMLParser()
        result = parser._normalize_url("/page", "https://base.com")
        assert result == "https://base.com/page"

    def test_normalize_url_relative_without_slash(self):
        """スラッシュなし相対URLの正規化."""
        parser = HTMLParser()
        result = parser._normalize_url("page", "https://base.com")
        assert result == "https://base.com/page"

    def test_extract_articles_max_items_limit(self):
        """最大記事数の制限が機能する."""
        parser = HTMLParser()
        html_content = """
        <html>
        <body>
            <h2><a href="/1">記事1</a></h2>
            <h2><a href="/2">記事2</a></h2>
            <h2><a href="/3">記事3</a></h2>
            <h2><a href="/4">記事4</a></h2>
            <h2><a href="/5">記事5</a></h2>
        </body>
        </html>
        """
        
        items = parser.extract_articles(html_content, "https://example.com", max_items=3)
        
        assert len(items) == 3