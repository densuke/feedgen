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