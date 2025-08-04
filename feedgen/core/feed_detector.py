"""既存フィード検出・取得機能."""

from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .exceptions import FeedGenerationError


class FeedDetector:
    """既存フィード検出・取得クラス."""

    def __init__(self, user_agent: str = "feedgen/1.0") -> None:
        """初期化.
        
        Args:
            user_agent: User-Agentヘッダー

        """
        self.user_agent = user_agent

        # 一般的なフィードパス
        self.common_feed_paths = [
            "/feed",
            "/rss",
            "/atom.xml",
            "/rss.xml",
            "/feed.xml",
            "/feeds/all.atom.xml",
            "/rss/index.xml",
            "/feed/index.xml",
        ]

    def detect_feeds(self, url: str) -> list[dict[str, str]]:
        """URLからフィードを検出.
        
        Args:
            url: 検出対象のURL
            
        Returns:
            フィード情報のリスト（各要素: {url, title, type}）
            
        Raises:
            FeedGenerationError: フィード検出に失敗した場合

        """
        feeds = []

        try:
            # HTMLを取得してlinkタグを確認
            feeds.extend(self._detect_from_html(url))

            # 一般的なフィードパスを確認
            if not feeds:  # HTMLから見つからない場合のみ
                feeds.extend(self._detect_from_common_paths(url))

            return feeds

        except Exception as e:
            raise FeedGenerationError(f"フィード検出に失敗しました: {e}")

    def fetch_feed(self, feed_url: str) -> tuple[str, str]:
        """既存フィードを取得.
        
        Args:
            feed_url: フィードのURL
            
        Returns:
            (フィード内容, Content-Type)のタプル
            
        Raises:
            FeedGenerationError: フィード取得に失敗した場合

        """
        try:
            headers = {"User-Agent": self.user_agent}
            response = requests.get(feed_url, headers=headers, timeout=30)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "application/xml")
            return response.text, content_type

        except requests.RequestException as e:
            raise FeedGenerationError(f"フィード取得に失敗しました: {e}")

    def _detect_from_html(self, url: str) -> list[dict[str, str]]:
        """HTMLのlinkタグからフィードを検出."""
        feeds = []

        try:
            headers = {"User-Agent": self.user_agent}
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # RSS/Atomフィードのlinkタグを探す
            feed_links = soup.find_all("link", rel="alternate")

            for link in feed_links:
                link_type = link.get("type", "").lower()
                href = link.get("href", "")
                title = link.get("title", "不明なフィード")

                if self._is_feed_type(link_type) and href:
                    feed_url = urljoin(url, href)
                    feeds.append({
                        "url": feed_url,
                        "title": title,
                        "type": self._normalize_feed_type(link_type),
                    })

            return feeds

        except requests.RequestException:
            # HTMLが取得できない場合は空のリストを返す
            return []

    def _detect_from_common_paths(self, url: str) -> list[dict[str, str]]:
        """一般的なフィードパスから検出."""
        feeds = []
        base_url = self._get_base_url(url)

        for path in self.common_feed_paths:
            feed_url = base_url.rstrip("/") + path

            if self._check_feed_exists(feed_url):
                feed_type = self._guess_feed_type_from_path(path)
                feeds.append({
                    "url": feed_url,
                    "title": f"{urlparse(base_url).netloc} - {feed_type}",
                    "type": feed_type,
                })

                # 最初に見つかったフィードで十分
                break

        return feeds

    def _is_feed_type(self, content_type: str) -> bool:
        """Content-Typeがフィード形式かを判定."""
        feed_types = [
            "application/rss+xml",
            "application/atom+xml",
            "application/xml",
            "text/xml",
            "application/json",  # JSON Feed
        ]

        return any(feed_type in content_type for feed_type in feed_types)

    def _normalize_feed_type(self, content_type: str) -> str:
        """Content-Typeを正規化."""
        if "rss" in content_type:
            return "RSS"
        if "atom" in content_type:
            return "Atom"
        if "json" in content_type:
            return "JSON"
        return "XML"

    def _get_base_url(self, url: str) -> str:
        """ベースURLを取得."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _check_feed_exists(self, feed_url: str) -> bool:
        """フィードURLが存在するかチェック."""
        try:
            headers = {"User-Agent": self.user_agent}
            response = requests.head(feed_url, headers=headers, timeout=10, allow_redirects=True)

            # 200番台またはフィード形式のContent-Type
            if response.status_code < 400:
                content_type = response.headers.get("content-type", "").lower()
                return self._is_feed_type(content_type) or "xml" in content_type

            return False

        except requests.RequestException:
            return False

    def _guess_feed_type_from_path(self, path: str) -> str:
        """パスからフィード形式を推測."""
        path = path.lower()
        if "atom" in path:
            return "Atom"
        if "json" in path:
            return "JSON"
        return "RSS"
