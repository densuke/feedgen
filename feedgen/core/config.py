"""設定ファイル読み込み機能."""

import os
from pathlib import Path
from typing import Any, Dict

import yaml

from .exceptions import FeedGenerationError


class ConfigManager:
    """設定ファイル管理クラス."""
    
    def __init__(self, config_path: str | None = None):
        """初期化.
        
        Args:
            config_path: 設定ファイルのパス（Noneの場合は自動検出）
        """
        self.config_path = self._find_config_file(config_path)
        self._config_cache: Dict[str, Any] | None = None
    
    def _find_config_file(self, config_path: str | None) -> Path | None:
        """設定ファイルを検索.
        
        Args:
            config_path: 指定された設定ファイルパス
            
        Returns:
            見つかった設定ファイルのパス（見つからない場合はNone）
        """
        if config_path:
            path = Path(config_path)
            if path.exists():
                return path
            raise FeedGenerationError(f"指定された設定ファイルが見つかりません: {config_path}")
        
        # 自動検出: カレントディレクトリから上位に向かって検索
        current_dir = Path.cwd()
        for directory in [current_dir] + list(current_dir.parents):
            config_file = directory / "config.yaml"
            if config_file.exists():
                return config_file
        
        return None
    
    def load_config(self) -> Dict[str, Any]:
        """設定ファイルを読み込み.
        
        Returns:
            設定辞書
            
        Raises:
            FeedGenerationError: 設定ファイル読み込みに失敗した場合
        """
        if self._config_cache is not None:
            return self._config_cache
        
        if not self.config_path:
            # 設定ファイルが見つからない場合は空の設定を返す
            self._config_cache = {}
            return self._config_cache
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            
            self._config_cache = config
            return config
            
        except yaml.YAMLError as e:
            raise FeedGenerationError(f"設定ファイルの解析に失敗しました: {e}")
        except Exception as e:
            raise FeedGenerationError(f"設定ファイルの読み込みに失敗しました: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """設定値を取得.
        
        Args:
            key: 設定キー
            default: デフォルト値
            
        Returns:
            設定値
        """
        config = self.load_config()
        return config.get(key, default)
    
    def get_youtube_api_key(self) -> str | None:
        """YouTube API Keyを取得.
        
        Returns:
            API Key（設定されていない場合はNone）
        """
        # 設定ファイルから取得を試す
        api_key = self.get("youtube_api_key")
        if api_key:
            return api_key
        
        # 環境変数から取得を試す
        return os.getenv("YOUTUBE_API_KEY")
    
    def has_config_file(self) -> bool:
        """設定ファイルが存在するかを確認.

        Returns:
            設定ファイルが存在する場合True
        """
        return self.config_path is not None

    def get_instagram_config(self) -> Dict[str, Any]:
        """Instagram設定を取得.

        Returns:
            Instagram設定辞書（設定されていない場合は空辞書）
        """
        config = self.load_config()
        return config.get("instagram", {})

    def get_instagram_username(self) -> str | None:
        """Instagram認証用ユーザー名を取得.

        Returns:
            ユーザー名（設定されていない場合はNone）
        """
        instagram_config = self.get_instagram_config()
        username = instagram_config.get("username")

        # 空文字列の場合はNoneを返す
        if not username:
            return None

        # 環境変数からも取得を試す
        return username or os.getenv("INSTAGRAM_USERNAME")

    def get_instagram_session_file(self) -> str | None:
        """Instagramセッションファイルパスを取得.

        Returns:
            セッションファイルパス（設定されていない場合はNone）
        """
        instagram_config = self.get_instagram_config()
        session_file = instagram_config.get("session_file")

        # 空文字列の場合はNoneを返す
        if not session_file:
            return None

        # 環境変数からも取得を試す
        return session_file or os.getenv("INSTAGRAM_SESSION_FILE")

    def use_instagram_full_client(self) -> bool:
        """Instagramフル機能版使用フラグを取得.

        Returns:
            フル機能版を使用する場合True（デフォルト: False）
        """
        instagram_config = self.get_instagram_config()
        return instagram_config.get("use_full_client", False)

    def get_instagram_max_posts(self) -> int:
        """Instagram最大投稿取得数を取得.

        Returns:
            最大投稿取得数（デフォルト: 20）
        """
        instagram_config = self.get_instagram_config()
        return instagram_config.get("max_posts", 20)