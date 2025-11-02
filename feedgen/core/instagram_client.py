"""Instagram専用クライアント.

軽量実装版: metaタグからプロフィール情報を取得
将来的な拡張: instaloaderを使用したフル機能実装
"""

import logging
import re
from typing import Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from feedgen.core.models import RSSFeed, RSSItem

logger = logging.getLogger(__name__)


class InstagramClient:
    """Instagram専用クライアント(軽量実装版)."""

    def __init__(
        self,
        user_agent: str = "Mozilla/5.0 (compatible; feedgen/1.0)",
        timeout: int = 10,
    ):
        """初期化.
        
        Args:
            user_agent: ユーザーエージェント
            timeout: タイムアウト秒数
        """
        self.user_agent = user_agent
        self.timeout = timeout

    def is_instagram_url(self, url: str) -> bool:
        """Instagram URLかどうかを判定.
        
        Args:
            url: 判定対象のURL
            
        Returns:
            Instagram URLの場合True
        """
        parsed = urlparse(url)
        return parsed.netloc in ("www.instagram.com", "instagram.com")

    def is_profile_url(self, url: str) -> bool:
        """プロフィールページのURLかを判定.
        
        Args:
            url: 判定対象のURL
            
        Returns:
            プロフィールURLの場合True
        """
        if not self.is_instagram_url(url):
            return False
        
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        
        # 空パスはプロフィールではない
        if not path or path == "/":
            return False
        
        # プロフィールURL以外のパターンを除外
        # /p/, /reel/, /tv/, /explore/, /stories/, /accounts/ などの機能URL
        excluded_paths = ("/p/", "/reel/", "/tv/", "/explore", "/stories/", "/accounts/", "/direct/")
        for excluded in excluded_paths:
            if path.startswith(excluded):
                return False
        
        # /@username または /username 形式のみ許可
        return bool(re.match(r"^/?@?\w+$", path))

    def fetch_profile_metadata(self, url: str) -> Optional[RSSFeed]:
        """プロフィールページからmetaタグを取得してRSSFeedを生成.
        
        Args:
            url: InstagramプロフィールURL
            
        Returns:
            RSSFeed（取得失敗時はNone）
        """
        try:
            headers = {"User-Agent": self.user_agent}
            response = httpx.get(url, headers=headers, timeout=self.timeout, follow_redirects=True)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # metaタグからデータを取得
            title = self._extract_meta_content(soup, "og:title") or "Instagram Profile"
            description = self._extract_meta_content(soup, "og:description") or ""
            image = self._extract_meta_content(soup, "og:image")

            # プロフィール情報をパース
            profile_info = self._parse_profile_description(description)

            # 現在の軽量実装では投稿詳細は取得できないため、
            # プロフィール情報のみをRSSItemとして追加
            items = []
            if profile_info:
                item = RSSItem(
                    title=f"{title}のプロフィール",
                    link=url,
                    description=self._format_profile_info(profile_info),
                )
                items.append(item)
            
            feed_data = RSSFeed(
                title=title,
                description=profile_info.get("bio", description),
                link=url,
                items=items,
            )

            logger.info(f"Instagram プロフィール情報を取得: {url}")
            return feed_data

        except httpx.HTTPError as e:
            logger.error(f"Instagram プロフィール取得エラー: {e}")
            return None
        except Exception as e:
            logger.error(f"Instagram パースエラー: {e}")
            return None

    def _extract_meta_content(self, soup: BeautifulSoup, property_name: str) -> Optional[str]:
        """metaタグからcontentを取得.
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_name: og:titleなどのプロパティ名
            
        Returns:
            content値（見つからない場合はNone）
        """
        meta_tag = soup.find("meta", property=property_name)
        if meta_tag and meta_tag.get("content"):
            return meta_tag.get("content")
        return None

    def _parse_profile_description(self, description: str) -> dict[str, str]:
        """プロフィールのdescriptionをパース.
        
        Instagram metaタグのdescription形式:
        "XXX Followers, YYY Following, ZZZ Posts - See Instagram photos and videos from ..."
        
        Args:
            description: og:descriptionの値
            
        Returns:
            パース結果の辞書
        """
        result = {}
        
        # フォロワー、フォロー、投稿数を抽出
        followers_match = re.search(r"(\d+(?:,\d+)*)\s+Followers?", description)
        following_match = re.search(r"(\d+(?:,\d+)*)\s+Following", description)
        posts_match = re.search(r"(\d+(?:,\d+)*)\s+Posts?", description)
        
        if followers_match:
            result["followers"] = followers_match.group(1)
        if following_match:
            result["following"] = following_match.group(1)
        if posts_match:
            result["posts"] = posts_match.group(1)
        
        # バイオ部分を抽出 (「"」で囲まれた部分)
        bio_match = re.search(r'"([^"]*)"', description)
        if bio_match:
            result["bio"] = bio_match.group(1)
        
        return result

    def _format_profile_info(self, profile_info: dict[str, str]) -> str:
        """プロフィール情報をフォーマット.
        
        Args:
            profile_info: プロフィール情報の辞書
            
        Returns:
            フォーマット済み文字列
        """
        parts = []
        
        if "followers" in profile_info:
            parts.append(f"フォロワー: {profile_info['followers']}")
        if "following" in profile_info:
            parts.append(f"フォロー中: {profile_info['following']}")
        if "posts" in profile_info:
            parts.append(f"投稿数: {profile_info['posts']}")
        
        stats = " | ".join(parts)
        
        if "bio" in profile_info:
            return f"{stats}\n\n{profile_info['bio']}"
        
        return stats
