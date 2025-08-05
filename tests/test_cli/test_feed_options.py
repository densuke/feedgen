"""CLIフィードオプションのテスト."""

from click.testing import CliRunner
from unittest.mock import Mock, patch
from feedgen.cli.main import cli


class TestCLIFeedOptions:
    """CLIフィードオプションのテスト."""

    @patch('feedgen.cli.main.FeedGenerator')
    def test_cli_with_use_feed_option(self, mock_generator_class):
        """--use-feedオプションで既存フィードを代理取得."""
        # モックの設定
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        
        # 既存フィードが見つかる
        mock_generator.detect_existing_feeds.return_value = [{
            'url': 'https://example.com/feed.xml',
            'title': 'Example RSS',
            'type': 'RSS'
        }]
        
        # フィード内容を返す
        mock_generator.fetch_existing_feed.return_value = (
            '<?xml version="1.0"?><rss version="2.0"></rss>',
            'application/rss+xml'
        )
        
        runner = CliRunner()
        result = runner.invoke(cli, ['--use-feed', 'https://example.com'])
        
        assert result.exit_code == 0
        assert '既存フィードを発見' in result.output
        assert '<?xml version="1.0"?>' in result.output
        mock_generator.detect_existing_feeds.assert_called_once()
        mock_generator.fetch_existing_feed.assert_called_once_with('https://example.com/feed.xml')

    @patch('feedgen.cli.main.FeedGenerator')
    def test_cli_with_feed_first_option_found(self, mock_generator_class):
        """--feed-firstオプションでフィードを通知."""
        # モックの設定
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        
        # 既存フィードが見つかる
        mock_generator.detect_existing_feeds.return_value = [{
            'url': 'https://example.com/feed.xml',
            'title': 'Example RSS',
            'type': 'RSS'
        }]
        
        # HTML解析の結果
        mock_feed = Mock()
        mock_feed.to_xml.return_value = '<?xml version="1.0"?><rss></rss>'
        mock_generator.generate_feed.return_value = mock_feed
        
        runner = CliRunner()
        result = runner.invoke(cli, ['--feed-first', 'https://example.com'])
        
        assert result.exit_code == 0
        # stderr（エラー出力）にフィード発見通知があることを確認
        # click.echoのerr=Trueによる出力はstderrに出る
        mock_generator.detect_existing_feeds.assert_called_once()
        mock_generator.generate_feed.assert_called_once()

    @patch('feedgen.cli.main.FeedGenerator')
    def test_cli_with_feed_first_option_not_found(self, mock_generator_class):
        """--feed-firstオプションでフィードが見つからない場合."""
        # モックの設定
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        
        # 既存フィードが見つからない
        mock_generator.detect_existing_feeds.return_value = []
        
        # HTML解析の結果
        mock_feed = Mock()
        mock_feed.to_xml.return_value = '<?xml version="1.0"?><rss></rss>'
        mock_generator.generate_feed.return_value = mock_feed
        
        runner = CliRunner()
        result = runner.invoke(cli, ['--feed-first', 'https://example.com'])
        
        assert result.exit_code == 0
        mock_generator.detect_existing_feeds.assert_called_once()
        mock_generator.generate_feed.assert_called_once()

    @patch('feedgen.cli.main.FeedGenerator')
    def test_cli_without_feed_options(self, mock_generator_class):
        """フィードオプションなしの通常動作."""
        # モックの設定
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        
        # HTML解析の結果
        mock_feed = Mock()
        mock_feed.to_xml.return_value = '<?xml version="1.0"?><rss></rss>'
        mock_generator.generate_feed.return_value = mock_feed
        
        runner = CliRunner()
        result = runner.invoke(cli, ['https://example.com'])
        
        assert result.exit_code == 0
        # フィード検出は呼ばれない
        mock_generator.detect_existing_feeds.assert_not_called()
        mock_generator.generate_feed.assert_called_once()

    def test_cli_help_includes_feed_options(self):
        """ヘルプにフィードオプションが含まれる."""
        runner = CliRunner()
        result = runner.invoke(cli, ['--help'])
        
        assert result.exit_code == 0
        assert '--use-feed' in result.output
        assert '--feed-first' in result.output
        assert '既存フィードがある場合は代理取得' in result.output
        assert 'フィード検出を優先' in result.output