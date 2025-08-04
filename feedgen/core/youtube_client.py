"""YouTube Data API v3クライアント."""

import os
from datetime import datetime
from typing import Optional
from urllib.parse import parse_qs, urlparse

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .exceptions import YouTubeAPIError
from .models import RSSItem


class YouTubeAPIClient:
    """YouTube Data API v3クライアントクラス."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        """初期化.
        
        Args:
            api_key: YouTube Data API v3のAPIキー
                    Noneの場合は環境変数YOUTUBE_API_KEYから取得
        
        Raises:
            YouTubeAPIError: APIキーが設定されていない場合
        """
        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY")
        if not self.api_key:
            raise YouTubeAPIError("YouTube API Keyが設定されていません")
        
        self.youtube = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        """YouTube APIクライアントを初期化."""
        try:
            self.youtube = build(
                "youtube",
                "v3",
                developerKey=self.api_key
            )
        except Exception as e:
            raise YouTubeAPIError(f"YouTube APIクライアントの初期化に失敗しました: {e}")

    def can_handle_url(self, url: str) -> bool:
        """指定されたURLがYouTube検索URLかを判定.
        
        Args:
            url: 判定対象のURL
            
        Returns:
            YouTube検索URLの場合True
        """
        parsed = urlparse(url)
        return (
            parsed.netloc == "www.youtube.com" and
            parsed.path == "/results" and
            "search_query" in parse_qs(parsed.query)
        )

    def extract_search_query(self, url: str) -> str:
        """YouTube検索URLから検索クエリを抽出.
        
        Args:
            url: YouTube検索URL
            
        Returns:
            検索クエリ文字列
            
        Raises:
            YouTubeAPIError: 検索クエリが抽出できない場合
        """
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        
        search_query = query_params.get("search_query")
        if not search_query:
            raise YouTubeAPIError("検索クエリが見つかりません")
        
        return search_query[0]

    def search_videos(self, query: str, max_results: int = 20) -> list[RSSItem]:
        """YouTube検索を実行してRSSItemのリストを返す.
        
        Args:
            query: 検索クエリ
            max_results: 最大結果数（1-50）
            
        Returns:
            検索結果のRSSItemリスト
            
        Raises:
            YouTubeAPIError: API呼び出しに失敗した場合
        """
        if not self.youtube:
            raise YouTubeAPIError("YouTube APIクライアントが初期化されていません")
        
        # maxResultsの範囲チェック
        max_results = max(1, min(50, max_results))
        
        try:
            # YouTube Data API v3のsearch.listを呼び出し
            request = self.youtube.search().list(
                part="snippet",
                q=query,
                type="video",
                maxResults=max_results,
                order="relevance"
            )
            response = request.execute()
            
            items = []
            for video in response.get("items", []):
                snippet = video.get("snippet", {})
                video_id = video.get("id", {}).get("videoId")
                
                if not video_id:
                    continue
                
                # 動画URLを構築
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                
                # 投稿日時を解析
                published_at = snippet.get("publishedAt", "")
                pub_date = datetime.now()
                if published_at:
                    try:
                        pub_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                    except ValueError:
                        pass  # パース失敗時は現在時刻を使用
                
                # 説明文を整形
                description = snippet.get("description", "")
                if len(description) > 300:
                    description = description[:300] + "..."
                
                # チャンネル名を追加
                channel_title = snippet.get("channelTitle", "")
                if channel_title and description:
                    description = f"チャンネル: {channel_title}\n\n{description}"
                elif channel_title:
                    description = f"チャンネル: {channel_title}"
                
                item = RSSItem(
                    title=snippet.get("title", "無題"),
                    description=description,
                    link=video_url,
                    guid=f"youtube-video-{video_id}",
                    pub_date=pub_date,
                )
                items.append(item)
            
            return items
            
        except HttpError as e:
            error_details = e.error_details[0] if e.error_details else {}
            reason = error_details.get("reason", "unknown")
            
            if reason == "quotaExceeded":
                raise YouTubeAPIError("YouTube APIのクォータを超過しました")
            elif reason == "keyInvalid":
                raise YouTubeAPIError("YouTube APIキーが無効です")
            else:
                raise YouTubeAPIError(f"YouTube API呼び出しエラー: {e}")
        
        except Exception as e:
            raise YouTubeAPIError(f"YouTube検索に失敗しました: {e}")

    def get_feed_from_url(self, url: str, max_results: int = 20) -> list[RSSItem]:
        """YouTube検索URLからRSSItemのリストを取得.
        
        Args:
            url: YouTube検索URL
            max_results: 最大結果数
            
        Returns:
            検索結果のRSSItemリスト
        """
        query = self.extract_search_query(url)
        return self.search_videos(query, max_results)