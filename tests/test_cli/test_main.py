"""CLIメイン機能のテスト."""

import pytest
from click.testing import CliRunner
from feedgen.cli.main import cli


class TestCLI:
    """CLI機能のテスト."""

    def test_cli_with_url_argument(self):
        """URL引数でCLIが実行できる."""
        runner = CliRunner()
        result = runner.invoke(cli, ['https://example.com'])
        
        assert result.exit_code == 0
        assert 'RSS' in result.output or 'xml' in result.output

    def test_cli_with_invalid_url_shows_error(self):
        """無効なURLでエラーメッセージが表示される."""
        runner = CliRunner()
        result = runner.invoke(cli, ['invalid-url'])
        
        assert result.exit_code != 0
        assert 'エラー' in result.output or 'Error' in result.output

    def test_cli_with_max_items_option(self):
        """--max-itemsオプションが機能する."""
        runner = CliRunner()
        result = runner.invoke(cli, ['--max-items', '5', 'https://example.com'])
        
        assert result.exit_code == 0

    def test_cli_with_output_file_option(self):
        """--outputオプションでファイル出力できる."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ['--output', 'test.xml', 'https://example.com'])
            
            assert result.exit_code == 0
            # ファイルが作成されることを確認
            with open('test.xml', 'r') as f:
                content = f.read()
                assert '<?xml' in content

    def test_cli_with_config_file_option(self):
        """--configオプションで設定ファイルが読み込める."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            # テスト用の設定ファイルを作成
            with open('test_config.yaml', 'w') as f:
                f.write("""
max_items: 10
user_agent: "test-agent/1.0"
""")
            
            result = runner.invoke(cli, ['--config', 'test_config.yaml', 'https://example.com'])
            assert result.exit_code == 0

    def test_cli_without_arguments_shows_help(self):
        """引数なしでヘルプが表示される."""
        runner = CliRunner()
        result = runner.invoke(cli, [])
        
        assert result.exit_code != 0
        assert 'Usage:' in result.output or '使用方法:' in result.output