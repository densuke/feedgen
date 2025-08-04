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