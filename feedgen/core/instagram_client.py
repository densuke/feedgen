# -*- coding: utf-8 -*-
import logging
import re
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from feedgen.core.models import RSSFeed, RSSItem
from feedgen.core.exceptions import InstagramAuthError, InstagramRateLimitError

logger = logging.getLogger(__name__)


class InstagramCache:
    """Instagram プロフィール取得結果のキャッシュ."""

    def __init__(self, ttl: int = 300):
        """初期化.

        Args:
            ttl: キャッシュの有効期限(秒)、デフォルト5分
        """
        self.ttl = ttl
        self._cache: dict[str, tuple[RSSFeed, float]] = {}
        self._stats = {"hits": 0, "misses": 0}

    def get(self, url: str) -> Optional[RSSFeed]:
        """キャッシュから取得.

        Args:
            url: プロフィールURL

        Returns:
            キャッシュされたRSSFeed(期限切れまたは存在しない場合はNone)
        """
        if url not in self._cache:
            self._stats["misses"] += 1
            return None

        feed, timestamp = self._cache[url]
        if time.time() - timestamp > self.ttl:
            # 期限切れ
            del self._cache[url]
            self._stats["misses"] += 1
            return None

        self._stats["hits"] += 1
        logger.info(f"Instagram キャッシュヒット: {url}")
        return feed

    def set(self, url: str, feed: RSSFeed) -> None:
        """キャッシュに保存.

        Args:
            url: プロフィールURL
            feed: RSSFeed
        """
        self._cache[url] = (feed, time.time())
        logger.info(f"Instagram キャッシュ保存: {url}")

    def clear(self) -> None:
        """キャッシュをクリア."""
        self._cache.clear()
        logger.info("Instagram キャッシュクリア")

    def get_stats(self) -> dict:
        """統計情報を取得.

        Returns:
            統計情報
        """
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total_requests if total_requests > 0 else 0

        return {
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "size": len(self._cache),
            "hit_rate": hit_rate,
        }


class InstagramClient:
    """Instagram専用クライアント(軽量実装版)."""

    def __init__(
        self,
        user_agent: str = "Mozilla/5.0 (compatible; feedgen/1.0)",
        timeout: int = 10,
        cache_ttl: int = 300,
        max_retries: int = 3,
    ):
        """初期化.

        Args:
            user_agent: ユーザーエージェント
            timeout: タイムアウト秒数
            cache_ttl: キャッシュ有効期限(秒)、デフォルト5分
            max_retries: 最大リトライ回数
        """
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries
        self._cache = InstagramCache(ttl=cache_ttl)

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

    def extract_profile_name(self, url: str) -> Optional[str]:
        """プロフィールURLからユーザー名を抽出.

        Args:
            url: InstagramプロフィールURL

        Returns:
            プロフィール名 (抽出できない場合はNone)
        """
        if not self.is_profile_url(url):
            return None

        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if not path:
            return None

        return path.lstrip("@")

    def fetch_profile_metadata(self, url: str) -> Optional[RSSFeed]:
        """プロフィールページからmetaタグを取得してRSSFeedを生成.

        Args:
            url: InstagramプロフィールURL

        Returns:
            RSSFeed(取得失敗時はNone)
        """
        # キャッシュチェック
        cached_feed = self._cache.get(url)
        if cached_feed:
            return cached_feed

        # リトライロジック付きで取得
        for attempt in range(self.max_retries):
            try:
                headers = {"User-Agent": self.user_agent}
                response = httpx.get(url, headers=headers, timeout=self.timeout, follow_redirects=True)

                # ログインページへのリダイレクトを検出
                if "/accounts/login/" in response.url.path:
                    error_msg = (
                        f"Instagram認証が必要: プロフィール '{url}' へのアクセスには認証が必要です。"
                        "InstagramFullClientの使用を検討してください。"
                    )
                    logger.error(error_msg)
                    raise InstagramAuthError(error_msg)

                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")

                # metaタグからデータを取得
                title = self._extract_meta_content(soup, "og:title") or "Instagram Profile"
                description = self._extract_meta_content(soup, "og:description") or ""
                self._extract_meta_content(soup, "og:image")

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

                # キャッシュに保存
                self._cache.set(url, feed_data)

                logger.info(f"Instagram プロフィール情報を取得: {url}")
                return feed_data

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    # レート制限エラー
                    wait_time = 2 ** attempt  # エクスポネンシャルバックオフ
                    logger.warning(
                        f"Instagram レート制限(429): {url} - "
                        f"リトライ {attempt + 1}/{self.max_retries} "
                        f"(待機: {wait_time}秒)"
                    )
                    if attempt < self.max_retries - 1:
                        time.sleep(wait_time)
                        continue
                    else:
                        error_msg = (
                            "Instagramレート制限: 最大リトライ回数に達しました。"
                            "しばらく待ってから再度アクセスするか、InstagramFullClientの使用を検討してください。"
                        )
                        logger.error(error_msg)
                        raise InstagramRateLimitError(error_msg)
                else:
                    logger.error(f"Instagram HTTPエラー {e.response.status_code}: {url}")
                    return None

            except httpx.HTTPError as e:
                logger.error(f"Instagram プロフィール取得エラー: {e}")
                return None
            except Exception as e:
                logger.error(f"Instagram パースエラー: {e}")
                return None

        return None

    def _extract_meta_content(self, soup: BeautifulSoup, property_name: str) -> Optional[str]:
        """metaタグからcontentを取得.
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_name: og:titleなどのプロパティ名
            
        Returns:
            content値(見つからない場合はNone)
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
class InstagramFullClient(InstagramClient):
    """Instagram専用クライアント(instaloader使用フル実装版).

    投稿詳細の取得が可能だが、認証が必要。
    """

    def __init__(
        self,
        username: str | None = None,
        session_file: str | None = None,
        max_posts: int = 20,
        user_agent: str = "Mozilla/5.0 (compatible; feedgen/1.0)",
        timeout: int = 10,
        cache_ttl: int = 300,
        max_retries: int = 3,
    ):
        """初期化.

        Args:
            username: Instagramのユーザー名(認証用)
            session_file: セッションファイルのパス
            max_posts: 取得する最大投稿数
            user_agent: ユーザーエージェント
            timeout: HTTPタイムアウト秒数
            cache_ttl: キャッシュ有効期限(秒)
            max_retries: 最大リトライ回数
        """
        super().__init__(user_agent=user_agent, timeout=timeout, cache_ttl=cache_ttl, max_retries=max_retries)
        self.username = username
        self.session_file = session_file
        self.max_posts = max_posts
        self._loader = None
        self._instaloader_available = False
        
        # instaloaderのインポートを試行
        try:
            import instaloader
            self._instaloader = instaloader
            self._instaloader_available = True
            logger.info("instaloader が利用可能です")
        except ImportError:
            logger.warning(
                "instaloader がインストールされていません。"
                "フル機能を使用するには 'pip install instaloader' を実行してください。"
            )

    def is_available(self) -> bool:
        """instaloaderが利用可能かを確認.
        
        Returns:
            instaloaderが利用可能な場合True
        """
        return self._instaloader_available

    def _get_loader(self):
        """Instaloaderインスタンスを取得(遅延初期化).
        
        Returns:
            Instaloaderインスタンス
            
        Raises:
            ImportError: instaloaderが利用不可の場合
        """
        if not self._instaloader_available:
            raise ImportError(
                "instaloader がインストールされていません。"
                "'pip install instaloader' を実行してください。"
            )
        
        if self._loader is None:
            self._loader = self._instaloader.Instaloader(
                download_pictures=False,
                download_videos=False,
                download_video_thumbnails=False,
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False,
            )
        
        return self._loader

    def login(self, password: str | None = None) -> bool:
        """Instagramにログイン.
        
        Args:
            password: パスワード(省略時はセッションファイルから読み込み)
            
        Returns:
            ログイン成功時True
        """
        if not self._instaloader_available:
            logger.error("instaloader が利用できません")
            return False
        
        loader = self._get_loader()
        
        try:
            # セッションファイルからの読み込みを試行
            if self.session_file and self.username:
                loader.load_session_from_file(self.username, self.session_file)
                logger.info(f"セッションファイルからログイン: {self.username}")
                return True
            
            # パスワードによるログイン
            if self.username and password:
                loader.login(self.username, password)
                logger.info(f"パスワードでログイン: {self.username}")
                
                # セッションを保存
                if self.session_file:
                    loader.save_session_to_file(self.session_file)
                    logger.info(f"セッションを保存: {self.session_file}")
                
                return True
            
            logger.warning("ユーザー名とパスワード、またはセッションファイルが必要です")
            return False
            
        except Exception as e:
            logger.error(f"ログインエラー: {e}")
            return False

    def fetch_profile_posts(self, profile_name: str) -> Optional[RSSFeed]:
        """プロフィールの投稿を取得してRSSFeedを生成.

        Args:
            profile_name: Instagramのプロフィール名

        Returns:
            RSSFeed(取得失敗時はNone)
        """
        if not self._instaloader_available:
            logger.error("instaloader が利用できません")
            return None

        # キャッシュキー生成
        cache_url = f"https://www.instagram.com/{profile_name}/"

        # キャッシュチェック
        cached_feed = self._cache.get(cache_url)
        if cached_feed:
            return cached_feed

        loader = self._get_loader()

        try:
            # プロフィールを取得
            profile = self._instaloader.Profile.from_username(loader.context, profile_name)

            # RSSアイテムのリスト
            items = []

            # 投稿を取得
            post_count = 0
            for post in profile.get_posts():
                if post_count >= self.max_posts:
                    break

                # 投稿をRSSItemに変換
                item = RSSItem(
                    title=self._get_post_title(post),
                    link=f"https://www.instagram.com/p/{post.shortcode}/",
                    description=self._format_post_description(post),
                    pub_date=post.date_utc,
                )
                items.append(item)
                post_count += 1

            # RSSFeedを生成
            feed = RSSFeed(
                title=f"{profile.full_name} (@{profile.username}) - Instagram",
                description=profile.biography or f"{profile.username}のInstagramフィード",
                link=f"https://www.instagram.com/{profile.username}/",
                items=items,
            )

            feed.last_build_date = datetime.now()

            # キャッシュに保存
            self._cache.set(cache_url, feed)

            logger.info(f"プロフィール投稿を取得: {profile_name} ({len(items)}件)")
            return feed

        except Exception as e:
            logger.error(f"プロフィール投稿取得エラー: {e}")
            return None

    def _get_post_title(self, post) -> str:
        """投稿のタイトルを生成.
        
        Args:
            post: Instaloaderの投稿オブジェクト
            
        Returns:
            タイトル文字列
        """
        # キャプションの最初の行をタイトルとして使用
        if post.caption:
            first_line = post.caption.split('\n')[0]
            # 長すぎる場合は切り詰め
            if len(first_line) > 100:
                return first_line[:97] + "..."
            return first_line
        
        # キャプションがない場合
        if post.is_video:
            return f"動画投稿 - {post.date_utc.strftime('%Y-%m-%d')}"
        else:
            return f"写真投稿 - {post.date_utc.strftime('%Y-%m-%d')}"

    def _format_post_description(self, post) -> str:
        """投稿の説明を生成.
        
        Args:
            post: Instaloaderの投稿オブジェクト
            
        Returns:
            説明文字列
        """
        parts = []
        
        # 投稿タイプ
        if post.is_video:
            parts.append("📹 動画投稿")
        elif post.typename == "GraphSidecar":
            parts.append(f"🖼️ 複数画像投稿 ({post.mediacount}枚)")
        else:
            parts.append("🖼️ 画像投稿")
        
        # いいね数とコメント数
        parts.append(f"❤️ {post.likes:,} いいね")
        parts.append(f"💬 {post.comments:,} コメント")
        
        stats = " | ".join(parts)
        
        # キャプション
        if post.caption:
            return f"{stats}\n\n{post.caption}"
        
        return stats
