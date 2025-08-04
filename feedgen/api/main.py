"""Web API for RSS feed generation."""

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from ..core import FeedGenerator
from ..core.config import ConfigManager
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
            "feed": "/feed?url=<target_url>&max_items=<number>&use_feed=<boolean>&feed_first=<boolean>&user_agent=<string>",
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
):
    """RSSフィードを生成または代理取得する.
    
    Args:
        url: 分析対象のURL
        max_items: 最大記事数（1-100）
        use_feed: 既存フィード代理取得
        feed_first: フィード検出優先
        user_agent: User-Agentヘッダー
        
    Returns:
        RSS XML形式のレスポンス
        
    Raises:
        HTTPException: フィード生成に失敗した場合
        
    """
    try:
        # 設定準備
        config = {
            "max_items": max_items,
            "user_agent": user_agent,
        }
        
        # 設定ファイルからYouTube API Keyを読み込み
        config_manager = ConfigManager()
        youtube_api_key = config_manager.get_youtube_api_key()
        generator = FeedGenerator(youtube_api_key=youtube_api_key)
        
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