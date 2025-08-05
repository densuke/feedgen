"""設定管理モジュール."""

from pathlib import Path
from typing import Any

import yaml
from ..core.google_news_decoder import GoogleNewsDecoderConfig


class ConfigManager:
    """設定管理クラス."""

    def get_default_config(self) -> dict[str, Any]:
        """デフォルト設定を取得.
        
        Returns:
            デフォルト設定の辞書

        """
        return {
            "max_items": 20,
            "cache_duration": 3600,
            "user_agent": "feedgen/1.0",
            "api_base_url": None,  # Web API のベースURL（例: https://example.com）
            "google_news": {
                "decode_enabled": False,
                "request_interval": 1,
                "request_timeout": 10,
                "max_retries": 3,
                "enable_logging": True,
            },
        }

    def load_config(self, config_path: str) -> dict[str, Any]:
        """設定ファイルを読み込み.
        
        Args:
            config_path: 設定ファイルのパス
            
        Returns:
            設定の辞書
            
        Raises:
            FileNotFoundError: ファイルが存在しない場合
            yaml.YAMLError: YAML解析エラーの場合

        """
        config_file = Path(config_path)

        if not config_file.exists():
            raise FileNotFoundError(f"設定ファイルが見つかりません: {config_path}")

        try:
            with open(config_file, encoding="utf-8") as f:
                config = yaml.safe_load(f)
                return config if config is not None else {}
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"設定ファイルの解析に失敗しました: {e}")

    def merge_configs(self, base_config: dict[str, Any], override_config: dict[str, Any]) -> dict[str, Any]:
        """設定をマージ.
        
        Args:
            base_config: ベース設定
            override_config: オーバーライド設定
            
        Returns:
            マージされた設定

        """
        merged = base_config.copy()
        
        # 通常の設定項目をマージ
        for key, value in override_config.items():
            if key == "google_news" and isinstance(value, dict) and key in merged:
                # google_news設定は深いマージを行う
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
                
        return merged

    def get_google_news_config(self, config: dict[str, Any]) -> GoogleNewsDecoderConfig:
        """Google News デコーダー設定を取得.
        
        Args:
            config: 全体設定
            
        Returns:
            Google News デコーダー設定
        """
        google_news_config = config.get("google_news", {})
        return GoogleNewsDecoderConfig.from_dict(google_news_config)
