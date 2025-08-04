"""CLI URL生成機能のテスト."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from feedgen.cli.main import cli


class TestCLIURLGeneration:
    """CLI URL生成機能のテスト."""

    def setup_method(self):
        """テストセットアップ."""
        self.runner = CliRunner()

    def test_generate_url_with_api_host_option(self):
        """--api-hostオプションでのURL生成をテスト."""
        result = self.runner.invoke(cli, [
            "--generate-url",
            "--api-host", "https://feedgen.example.com",
            "https://target.com"
        ])
        
        assert result.exit_code == 0
        assert "https://feedgen.example.com/feed?url=https%3A%2F%2Ftarget.com" in result.output

    def test_generate_url_with_all_options(self):
        """全オプション指定でのURL生成をテスト."""
        result = self.runner.invoke(cli, [
            "--generate-url",
            "--api-host", "https://api.example.com",
            "--max-items", "5",
            "--use-feed",
            "--feed-first",
            "--user-agent", "test-agent/1.0",
            "https://blog.example.com"
        ])
        
        assert result.exit_code == 0
        output_url = result.output.strip()
        
        # 各パラメータが含まれていることを確認
        assert "https://api.example.com/feed?" in output_url
        assert "url=https%3A%2F%2Fblog.example.com" in output_url
        assert "max_items=5" in output_url
        assert "use_feed=true" in output_url
        assert "feed_first=true" in output_url
        assert "user_agent=test-agent%2F1.0" in output_url

    def test_generate_url_without_api_host_fails(self):
        """APIホスト未指定でのURL生成がエラーになることをテスト."""
        result = self.runner.invoke(cli, [
            "--generate-url",
            "https://target.com"
        ])
        
        assert result.exit_code == 1
        assert "APIホストが指定されていません" in result.output

    def test_generate_url_with_config_file(self):
        """設定ファイルからAPIホストを読み込んでのURL生成をテスト."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
api_base_url: https://config.example.com
max_items: 30
user_agent: config-agent/1.0
""")
            config_path = f.name

        try:
            result = self.runner.invoke(cli, [
                "--generate-url",
                "--config", config_path,
                "https://target.com"
            ])
            
            assert result.exit_code == 0
            assert "https://config.example.com/feed?url=https%3A%2F%2Ftarget.com" in result.output
            
        finally:
            Path(config_path).unlink()

    def test_generate_url_cli_overrides_config(self):
        """コマンドラインオプションが設定ファイルを上書きすることをテスト."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
api_base_url: https://config.example.com
max_items: 30
""")
            config_path = f.name

        try:
            result = self.runner.invoke(cli, [
                "--generate-url",
                "--config", config_path,
                "--api-host", "https://cli.example.com",
                "--max-items", "10",
                "https://target.com"
            ])
            
            assert result.exit_code == 0
            output_url = result.output.strip()
            
            # CLIオプションが優先されることを確認
            assert "https://cli.example.com/feed?" in output_url
            assert "max_items=10" in output_url
            
        finally:
            Path(config_path).unlink()

    def test_generate_url_with_output_file(self):
        """出力ファイル指定でのURL生成をテスト."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            output_path = f.name

        try:
            result = self.runner.invoke(cli, [
                "--generate-url",
                "--api-host", "https://example.com",
                "--output", output_path,
                "https://target.com"
            ])
            
            assert result.exit_code == 0
            assert f"API URLを出力しました: {output_path}" in result.output
            
            # ファイル内容を確認
            with open(output_path, encoding="utf-8") as f:
                url_content = f.read().strip()
                assert "https://example.com/feed?url=https%3A%2F%2Ftarget.com" == url_content
                
        finally:
            Path(output_path).unlink()

    def test_generate_url_normalizes_host(self):
        """ホスト名の正規化をテスト."""
        result = self.runner.invoke(cli, [
            "--generate-url",
            "--api-host", "example.com",  # プロトコルなし
            "https://target.com"
        ])
        
        assert result.exit_code == 0
        assert "https://example.com/feed?url=https%3A%2F%2Ftarget.com" in result.output

    def test_generate_url_removes_trailing_slash(self):
        """末尾スラッシュの除去をテスト."""
        result = self.runner.invoke(cli, [
            "--generate-url",
            "--api-host", "https://example.com/",  # 末尾スラッシュあり
            "https://target.com"
        ])
        
        assert result.exit_code == 0
        assert "https://example.com/feed?url=https%3A%2F%2Ftarget.com" in result.output

    def test_generate_url_validates_invalid_host(self):
        """無効なホストの検証をテスト."""
        result = self.runner.invoke(cli, [
            "--generate-url",
            "--api-host", "",  # 空文字
            "https://target.com"
        ])
        
        assert result.exit_code == 1
        assert "APIホストが指定されていません" in result.output

    def test_generate_url_does_not_generate_feed(self):
        """URL生成モードではフィード生成を行わないことをテスト."""
        with patch("feedgen.cli.main.FeedGenerator") as mock_generator:
            result = self.runner.invoke(cli, [
                "--generate-url",
                "--api-host", "https://example.com",
                "https://target.com"
            ])
            
            assert result.exit_code == 0
            # FeedGeneratorが初期化されていないことを確認
            mock_generator.assert_not_called()

    def test_generate_url_help_text(self):
        """ヘルプテキストにURL生成オプションが含まれることをテスト."""
        result = self.runner.invoke(cli, ["--help"])
        
        assert result.exit_code == 0
        assert "--generate-url" in result.output
        assert "--api-host" in result.output
        assert "Web API用のURLを生成して出力" in result.output
        assert "Web APIのホスト名" in result.output