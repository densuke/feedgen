"""Web API for RSS feed generation."""

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from ..core import FeedGenerator
from ..cli.config import ConfigManager
from ..core.exceptions import FeedGenerationError, ParseError

app = FastAPI(
    title="feedgen API",
    description="URL-to-RSS feed generation service with existing feed detection",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """API情報を返す."""
    return {
        "service": "feedgen API",
        "version": "1.0.0",
        "description": "URL-to-RSS feed generation with existing feed detection",
        "endpoints": {
            "feed": "/feed?url=<target_url>&max_items=<number>&use_feed=<boolean>&feed_first=<boolean>&user_agent=<string>&decode_google_news=<boolean>&google_news_interval=<number>&google_news_timeout=<number>&google_news_cache_ttl=<number>&google_news_cache_type=<string>",
            "docs": "/docs",
        },
    }


@app.get("/feed")
async def generate_feed(
    url: str = Query(..., description="分析対象のURL"),
    max_items: Optional[int] = Query(20, description="最大記事数", ge=1, le=100),
    use_feed: Optional[bool] = Query(False, description="既存フィード代理取得"),
    feed_first: Optional[bool] = Query(False, description="フィード検出優先"),
    user_agent: Optional[str] = Query("feedgen-api/1.0", description="User-Agentヘッダー"),
    decode_google_news: Optional[bool] = Query(False, description="Google News URLデコード有効化"),
    google_news_interval: Optional[int] = Query(1, description="Google Newsデコード処理間隔（秒）", ge=1, le=60),
    google_news_timeout: Optional[int] = Query(10, description="Google Newsデコード処理タイムアウト（秒）", ge=5, le=120),
    google_news_cache_ttl: Optional[int] = Query(86400, description="Google Newsキャッシュ有効期限（秒）", ge=300, le=604800),
    google_news_cache_type: Optional[str] = Query("memory", description="Google Newsキャッシュタイプ", regex="^(memory|redis)$"),
):
    """RSSフィードを生成または代理取得する.
    
    Args:
        url: 分析対象のURL
        max_items: 最大記事数（1-100）
        use_feed: 既存フィード代理取得
        feed_first: フィード検出優先
        user_agent: User-Agentヘッダー
        decode_google_news: Google News URLデコード有効化
        google_news_interval: Google Newsデコード処理間隔（秒）
        google_news_timeout: Google Newsデコード処理タイムアウト（秒）
        google_news_cache_ttl: Google Newsキャッシュ有効期限（秒）
        google_news_cache_type: Google Newsキャッシュタイプ
        
    Returns:
        RSS XML形式のレスポンス
        
    Raises:
        HTTPException: フィード生成に失敗した場合
        
    """
    try:
        # 設定準備
        config_manager = ConfigManager()
        base_config = config_manager.get_default_config()
        
        # パラメータで設定をオーバーライド
        config = {
            **base_config,
            "max_items": max_items,
            "user_agent": user_agent,
        }
        
        # Google News設定
        if (decode_google_news or google_news_interval != 1 or google_news_timeout != 10 or
            google_news_cache_ttl != 86400 or google_news_cache_type != "memory"):
            google_news_config = config.get("google_news", {})
            
            if decode_google_news:
                google_news_config["decode_enabled"] = True
            if google_news_interval is not None:
                google_news_config["request_interval"] = google_news_interval
            if google_news_timeout is not None:
                google_news_config["request_timeout"] = google_news_timeout
            if google_news_cache_ttl is not None:
                google_news_config["cache_ttl"] = google_news_cache_ttl
            if google_news_cache_type is not None:
                google_news_config["cache_type"] = google_news_cache_type
                
            config["google_news"] = google_news_config
        
        # YouTube API Keyを取得（存在する場合）
        youtube_api_key = getattr(config_manager, 'get_youtube_api_key', lambda: None)()

        # Google News設定を取得
        google_news_config = config_manager.get_google_news_config(config)

        # Instagram設定を取得
        instagram_username = getattr(config_manager, 'get_instagram_username', lambda: None)()
        instagram_session_file = getattr(config_manager, 'get_instagram_session_file', lambda: None)()
        instagram_max_posts = getattr(config_manager, 'get_instagram_max_posts', lambda: 20)()
        use_instagram_full_client = getattr(config_manager, 'use_instagram_full_client', lambda: False)()

        generator = FeedGenerator(
            youtube_api_key=youtube_api_key,
            google_news_config=google_news_config,
            instagram_username=instagram_username,
            instagram_session_file=instagram_session_file,
            instagram_max_posts=instagram_max_posts,
            use_instagram_full_client=use_instagram_full_client
        )
        
        # フィード検出・代理取得ロジック
        if use_feed or feed_first:
            try:
                existing_feeds = generator.detect_existing_feeds(url)
                
                if existing_feeds:
                    if use_feed:
                        # 代理取得モード
                        feed_info = existing_feeds[0]
                        xml_content, content_type = generator.fetch_existing_feed(feed_info["url"])
                        
                        # Content-Typeを正規化
                        if "rss" in content_type.lower():
                            response_content_type = "application/rss+xml; charset=utf-8"
                        elif "atom" in content_type.lower():
                            response_content_type = "application/atom+xml; charset=utf-8"
                        else:
                            response_content_type = "application/xml; charset=utf-8"
                            
                        return Response(
                            content=xml_content,
                            media_type=response_content_type,
                        )
                    elif feed_first:
                        # 通知のみ（ヘッダーに情報追加）
                        feed_info = existing_feeds[0]
                        # feed_firstの場合はHTML解析に続行
                        pass
                        
            except (FeedGenerationError, ParseError):
                # フィード検出/取得に失敗した場合はHTML解析に続行
                pass
        
        # HTML解析によるフィード生成
        feed = generator.generate_feed(url, config=config)
        xml_content = feed.to_xml()
        
        # レスポンスヘッダー準備
        headers = {}
        if feed_first and "existing_feeds" in locals() and existing_feeds:
            # 既存フィード情報をヘッダーに含める
            feed_info = existing_feeds[0]
            headers["X-Existing-Feed-URL"] = feed_info["url"]
            headers["X-Existing-Feed-Title"] = feed_info["title"]
            headers["X-Existing-Feed-Type"] = feed_info["type"]
        
        return Response(
            content=xml_content,
            media_type="application/rss+xml; charset=utf-8",
            headers=headers,
        )
        
    except (FeedGenerationError, ParseError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/health")
async def health_check():
    """ヘルスチェック用エンドポイント."""
    return {"status": "healthy", "service": "feedgen API"}


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(app, host="0.0.0.0", port=8000)