"""HTML解析機能."""

from datetime import datetime

import requests
from bs4 import BeautifulSoup

from .exceptions import FeedGenerationError, ParseError
from .models import RSSItem
from .url_normalizers import URLNormalizerRegistry


class HTMLParser:
    """HTML解析クラス."""

    def __init__(self, user_agent: str = "feedgen/1.0") -> None:
        """初期化.
        
        Args:
            user_agent: User-Agentヘッダー

        """
        self.user_agent = user_agent
        self.url_normalizer_registry = URLNormalizerRegistry()

    def fetch_content(self, url: str) -> str:
        """URLからHTMLコンテンツを取得.
        
        Args:
            url: 取得対象のURL
            
        Returns:
            HTMLコンテンツ
            
        Raises:
            FeedGenerationError: コンテンツ取得に失敗した場合

        """
        try:
            headers = {"User-Agent": self.user_agent}
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            raise FeedGenerationError(f"URLからのコンテンツ取得に失敗しました: {e}")

    def parse_metadata(self, html_content: str, url: str) -> dict[str, str]:
        """HTMLからメタデータを抽出.
        
        Args:
            html_content: HTMLコンテンツ
            url: 元のURL
            
        Returns:
            メタデータの辞書（title, description, link）
            
        Raises:
            ParseError: HTML解析に失敗した場合

        """
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # タイトルを取得
            title_tag = soup.find("title")
            title = title_tag.get_text().strip() if title_tag else "無題"

            # 説明を取得（meta descriptionから）
            description_tag = soup.find("meta", attrs={"name": "description"})
            description = ""
            if description_tag and description_tag.get("content"):
                description = description_tag["content"].strip()
            else:
                # fallback: 最初のpタグの内容
                first_p = soup.find("p")
                if first_p:
                    description = first_p.get_text().strip()[:200] + "..."

            return {
                "title": title,
                "description": description,
                "link": url,
            }
        except Exception as e:
            raise ParseError(f"HTML解析に失敗しました: {e}")

    def extract_articles(self, html_content: str, base_url: str, max_items: int = 20) -> list[RSSItem]:
        """HTMLから記事一覧を抽出.
        
        Args:
            html_content: HTMLコンテンツ
            base_url: ベースURL
            max_items: 最大記事数
            
        Returns:
            RSS記事アイテムのリスト
            
        Raises:
            ParseError: HTML解析に失敗した場合

        """
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            items = []

            # 複数の抽出戦略を試す
            items.extend(self._extract_from_headings_with_links(soup, base_url, max_items))

            if len(items) < max_items:
                remaining = max_items - len(items)
                items.extend(self._extract_from_card_elements(soup, base_url, remaining))

            if len(items) < max_items:
                remaining = max_items - len(items)
                items.extend(self._extract_from_content_blocks(soup, base_url, remaining))

            # 重複排除（タイトルベース）
            items = self._deduplicate_items(items)

            return items[:max_items]
        except Exception as e:
            raise ParseError(f"記事抽出に失敗しました: {e}")

    def _extract_from_headings_with_links(self, soup: BeautifulSoup, base_url: str, max_items: int) -> list[RSSItem]:
        """見出しタグ内のリンクから記事を抽出."""
        items = []
        article_tags = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"], limit=max_items * 2)

        for i, tag in enumerate(article_tags):
            if len(items) >= max_items:
                break

            link_tag = tag.find("a")
            if link_tag and link_tag.get("href"):
                href = self._normalize_url(link_tag["href"], base_url)
                title = tag.get_text().strip()

                if title and href:
                    description = self._get_description_for_element(tag)

                    item = RSSItem(
                        title=title,
                        description=description,
                        link=href,
                        guid=f"{base_url}#heading-{i}",
                        pub_date=datetime.now(),
                    )
                    items.append(item)

        return items

    def _extract_from_card_elements(self, soup: BeautifulSoup, base_url: str, max_items: int) -> list[RSSItem]:
        """カード形式の要素から記事を抽出（TailwindCSS等のmodernサイト対応）."""
        items = []

        # カード的な要素を探す（bg-content, card, cursor-pointer等のクラス）
        card_selectors = [
            '[class*="content"]',
            '[class*="card"]',
            '[class*="cursor-pointer"]',
            "article",
            '[class*="item"]',
        ]

        for selector in card_selectors:
            if len(items) >= max_items:
                break

            cards = soup.select(selector)[:max_items * 2]

            for i, card in enumerate(cards):
                if len(items) >= max_items:
                    break

                # カード内のテキスト取得
                text = card.get_text().strip()
                if len(text) < 10:  # 短すぎるものは除外
                    continue

                # タイトルを抽出（最初の行または見出し要素）
                title = self._extract_title_from_card(card, text)

                # 説明を抽出
                description = text[:200] + "..." if len(text) > 200 else text

                # リンクを探す（カード全体がクリッカブルな場合やリンクが含まれる場合）
                link = self._extract_link_from_card(card, base_url)

                if title and (link or len(title) > 5):  # リンクがなくても有用な情報があれば含める
                    # リンクがない場合はベースURLを使用
                    actual_link = link if link else base_url

                    item = RSSItem(
                        title=title,
                        description=description,
                        link=actual_link,
                        guid=f"{base_url}#card-{len(items)}",
                        pub_date=datetime.now(),
                    )
                    items.append(item)

        return items

    def _extract_from_content_blocks(self, soup: BeautifulSoup, base_url: str, max_items: int) -> list[RSSItem]:
        """コンテンツブロックから記事を抽出（フォールバック）."""
        items = []

        # pタグやdivタグで長めのテキストを持つものを探す
        content_blocks = soup.find_all(["p", "div"], limit=max_items * 3)

        for i, block in enumerate(content_blocks):
            if len(items) >= max_items:
                break

            text = block.get_text().strip()
            if len(text) < 30:  # 短すぎるものは除外
                continue

            # 近くのリンクを探す
            link = None
            link_tag = block.find("a")
            if link_tag and link_tag.get("href"):
                link = self._normalize_url(link_tag["href"], base_url)

            if link:  # リンクがある場合のみ含める
                title = text.split("\n")[0][:100]  # 最初の行をタイトルに
                description = text[:200] + "..." if len(text) > 200 else text

                item = RSSItem(
                    title=title,
                    description=description,
                    link=link,
                    guid=f"{base_url}#content-{i}",
                    pub_date=datetime.now(),
                )
                items.append(item)

        return items

    def _extract_title_from_card(self, card, full_text: str) -> str:
        """カード要素からタイトルを抽出."""
        # 見出しタグがあればそれを使用
        heading = card.find(["h1", "h2", "h3", "h4", "h5", "h6"])
        if heading:
            return heading.get_text().strip()

        # 最初の行を使用（改行で分割）
        lines = full_text.split("\n")
        for line in lines:
            line = line.strip()
            if len(line) > 5 and len(line) < 200:  # 適切な長さ
                return line

        # フォールバック: 最初の100文字
        return full_text[:100] + "..." if len(full_text) > 100 else full_text

    def _extract_link_from_card(self, card, base_url: str) -> str:
        """カード要素からリンクを抽出."""
        # カード内のaタグを探す
        link_tag = card.find("a")
        if link_tag and link_tag.get("href"):
            return self._normalize_url(link_tag["href"], base_url)

        # data-*属性でリンクが指定されている場合
        for attr in ["data-href", "data-url", "data-link"]:
            if card.get(attr):
                return self._normalize_url(card[attr], base_url)

        return None

    def _normalize_url(self, href: str, base_url: str) -> str:
        """URLを正規化（相対URL→絶対URL変換）."""
        return self.url_normalizer_registry.normalize(href, base_url)

    def _get_description_for_element(self, element) -> str:
        """要素の説明を取得."""
        # 次の段落を探す
        next_elem = element.find_next(["p", "div"])
        if next_elem:
            text = next_elem.get_text().strip()
            return text[:200] + "..." if len(text) > 200 else text

        # 親要素内の他のテキストを探す
        parent = element.parent
        if parent:
            text = parent.get_text().strip()
            # 元の要素のテキストを除外
            element_text = element.get_text().strip()
            if text.startswith(element_text):
                remaining = text[len(element_text):].strip()
                return remaining[:200] + "..." if len(remaining) > 200 else remaining

        return ""

    def _deduplicate_items(self, items: list[RSSItem]) -> list[RSSItem]:
        """記事アイテムの重複を排除."""
        seen_titles = set()
        unique_items = []

        for item in items:
            # タイトルを正規化（空白を削除、小文字に変換）
            normalized_title = item.title.strip().lower()

            if normalized_title not in seen_titles and len(normalized_title) > 0:
                seen_titles.add(normalized_title)
                unique_items.append(item)

        return unique_items
