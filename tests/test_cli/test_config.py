"""設定管理のテスト."""

import pytest
import tempfile
import os
from feedgen.cli.config import ConfigManager


class TestConfigManager:
    """設定管理のテスト."""

    def test_default_config(self):
        """デフォルト設定が正しく設定される."""
        config_manager = ConfigManager()
        config = config_manager.get_default_config()
        
        assert config['max_items'] == 20
        assert config['cache_duration'] == 3600
        assert 'user_agent' in config

    def test_load_yaml_config_file(self):
        """YAML設定ファイルが正しく読み込める."""
        config_manager = ConfigManager()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
max_items: 15
cache_duration: 1800
user_agent: "custom-agent/1.0"
""")
            config_file = f.name
        
        try:
            config = config_manager.load_config(config_file)
            
            assert config['max_items'] == 15
            assert config['cache_duration'] == 1800
            assert config['user_agent'] == "custom-agent/1.0"
        finally:
            os.unlink(config_file)

    def test_merge_configs(self):
        """設定のマージが正しく動作する."""
        config_manager = ConfigManager()
        
        base_config = {
            'max_items': 20,
            'cache_duration': 3600,
            'user_agent': 'feedgen/1.0'
        }
        
        override_config = {
            'max_items': 10,
            'custom_option': 'test'
        }
        
        merged = config_manager.merge_configs(base_config, override_config)
        
        assert merged['max_items'] == 10  # オーバーライドされる
        assert merged['cache_duration'] == 3600  # 元の値が保持される
        assert merged['custom_option'] == 'test'  # 新しい値が追加される

    def test_load_nonexistent_config_file_raises_error(self):
        """存在しない設定ファイルでエラーが発生する."""
        config_manager = ConfigManager()
        
        with pytest.raises(FileNotFoundError):
            config_manager.load_config('nonexistent_config.yaml')

    def test_load_invalid_yaml_raises_error(self):
        """無効なYAMLファイルでエラーが発生する."""
        config_manager = ConfigManager()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: content: [")
            config_file = f.name

        try:
            with pytest.raises(Exception):  # YAML parse error
                config_manager.load_config(config_file)
        finally:
            os.unlink(config_file)

    def test_get_translation_config_default(self):
        """デフォルトの翻訳設定が取得できる."""
        config_manager = ConfigManager()
        config = config_manager.get_default_config()

        translation_config = config_manager.get_translation_config(config)

        assert translation_config["enabled"] is False
        assert translation_config["api_key"] is None
        assert translation_config["model"] == "gemini-1.5-flash"
        assert translation_config["source_lang"] == "auto"
        assert translation_config["target_lang"] == "ja"
        assert translation_config["cache_enabled"] is True
        assert translation_config["cache_type"] == "memory"
        assert translation_config["cache_ttl"] == 86400
        assert translation_config["cache_max_size"] == 1000

    def test_get_translation_config_custom(self):
        """カスタム翻訳設定が取得できる."""
        config_manager = ConfigManager()

        config = {
            "translation": {
                "enabled": True,
                "api_key": "test-key",
                "model": "gemini-1.5-pro",
                "target_lang": "ko",
                "cache_ttl": 3600,
            }
        }

        translation_config = config_manager.get_translation_config(config)

        assert translation_config["enabled"] is True
        assert translation_config["api_key"] == "test-key"
        assert translation_config["model"] == "gemini-1.5-pro"
        assert translation_config["target_lang"] == "ko"
        assert translation_config["cache_ttl"] == 3600
        # デフォルト値がマージされている
        assert translation_config["source_lang"] == "auto"
        assert translation_config["cache_enabled"] is True

    def test_merge_configs_with_translation(self):
        """翻訳設定を含むマージが正しく動作する."""
        config_manager = ConfigManager()

        base_config = config_manager.get_default_config()
        override_config = {
            "translation": {
                "enabled": True,
                "api_key": "override-key"
            }
        }

        merged = config_manager.merge_configs(base_config, override_config)

        assert "translation" in merged
        assert merged["translation"]["enabled"] is True
        assert merged["translation"]["api_key"] == "override-key"