"""HTML解析機能."""

from typing import Dict, List
from bs4 import BeautifulSoup
import requests
from datetime import datetime
from .models import RSSItem
from .exceptions import ParseError, FeedGenerationError


class HTMLParser:
    """HTML解析クラス."""
    
    def __init__(self, user_agent: str = "feedgen/1.0") -> None:
        """初期化.
        
        Args:
            user_agent: User-Agentヘッダー
        """
        self.user_agent = user_agent
    
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
    
    def parse_metadata(self, html_content: str, url: str) -> Dict[str, str]:
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
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # タイトルを取得
            title_tag = soup.find('title')
            title = title_tag.get_text().strip() if title_tag else "無題"
            
            # 説明を取得（meta descriptionから）
            description_tag = soup.find('meta', attrs={'name': 'description'})
            description = ""
            if description_tag and description_tag.get('content'):
                description = description_tag['content'].strip()
            else:
                # fallback: 最初のpタグの内容
                first_p = soup.find('p')
                if first_p:
                    description = first_p.get_text().strip()[:200] + "..."
            
            return {
                "title": title,
                "description": description,
                "link": url
            }
        except Exception as e:
            raise ParseError(f"HTML解析に失敗しました: {e}")
    
    def extract_articles(self, html_content: str, base_url: str, max_items: int = 20) -> List[RSSItem]:
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
            soup = BeautifulSoup(html_content, 'html.parser')
            items = []
            
            # 一般的な記事構造を探す（h1, h2, h3タグから）
            # より高度な実装では、サイト毎の構造を分析する必要がある
            article_tags = soup.find_all(['h1', 'h2', 'h3'], limit=max_items)
            
            for i, tag in enumerate(article_tags):
                # リンクを探す
                link_tag = tag.find('a')
                if link_tag and link_tag.get('href'):
                    href = link_tag['href']
                    # 相対URLを絶対URLに変換
                    if href.startswith('/'):
                        href = base_url.rstrip('/') + href
                    elif not href.startswith('http'):
                        href = base_url.rstrip('/') + '/' + href.lstrip('/')
                    
                    title = tag.get_text().strip()
                    
                    # 説明を取得（次の段落から）
                    description = ""
                    next_elem = tag.find_next(['p', 'div'])
                    if next_elem:
                        description = next_elem.get_text().strip()[:200] + "..."
                    
                    item = RSSItem(
                        title=title,
                        description=description,
                        link=href,
                        guid=f"{base_url}#{i}",
                        pub_date=datetime.now()
                    )
                    items.append(item)
            
            return items
        except Exception as e:
            raise ParseError(f"記事抽出に失敗しました: {e}")