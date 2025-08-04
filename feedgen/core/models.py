"""RSSフィードのデータモデル."""

from typing import Dict, List, Optional
from pydantic import BaseModel
from datetime import datetime


class RSSItem(BaseModel):
    """RSS記事アイテム."""
    
    title: str
    description: str
    link: str
    pub_date: Optional[datetime] = None
    guid: Optional[str] = None


class RSSFeed(BaseModel):
    """RSSフィードモデル."""
    
    title: str
    description: str
    link: str
    items: List[RSSItem] = []
    last_build_date: Optional[datetime] = None
    
    def to_xml(self) -> str:
        """XML文字列として出力.
        
        Returns:
            RSS 2.0形式のXML文字列
        """
        from feedgenerator import Rss201rev2Feed
        
        feed = Rss201rev2Feed(
            title=self.title,
            link=self.link,
            description=self.description,
            lastmod=self.last_build_date
        )
        
        for item in self.items:
            feed.add_item(
                title=item.title,
                link=item.link,
                description=item.description,
                pubdate=item.pub_date,
                unique_id=item.guid
            )
        
        return feed.writeString('utf-8')
    
    def to_dict(self) -> Dict:
        """辞書形式として出力.
        
        Returns:
            フィードデータの辞書
        """
        return {
            "title": self.title,
            "description": self.description,
            "link": self.link,
            "items": [item.model_dump() for item in self.items],
            "last_build_date": self.last_build_date.isoformat() if self.last_build_date else None
        }