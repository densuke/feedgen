"""CLIメイン機能."""

import click
import sys
from typing import Optional
from pathlib import Path

from ..core import FeedGenerator
from ..core.exceptions import FeedGenerationError, ParseError
from .config import ConfigManager


@click.command()
@click.argument('url')
@click.option('--config', '-c', help='設定ファイルのパス')
@click.option('--output', '-o', help='出力ファイルのパス')
@click.option('--max-items', type=int, help='最大記事数')
@click.option('--user-agent', help='User-Agentヘッダー')
def cli(url: str, config: Optional[str], output: Optional[str], 
        max_items: Optional[int], user_agent: Optional[str]) -> None:
    """指定されたURLからRSSフィードを生成.
    
    Args:
        url: 分析対象のURL
        config: 設定ファイルのパス
        output: 出力ファイルのパス
        max_items: 最大記事数
        user_agent: User-Agentヘッダー
    """
    try:
        # 設定を読み込み
        config_manager = ConfigManager()
        feed_config = config_manager.get_default_config()
        
        # 設定ファイルがある場合は読み込んでマージ
        if config:
            try:
                file_config = config_manager.load_config(config)
                feed_config = config_manager.merge_configs(feed_config, file_config)
            except (FileNotFoundError, Exception) as e:
                click.echo(f"設定ファイル読み込みエラー: {e}", err=True)
                sys.exit(1)
        
        # コマンドライン引数で設定をオーバーライド
        if max_items is not None:
            feed_config['max_items'] = max_items
        if user_agent is not None:
            feed_config['user_agent'] = user_agent
        
        # フィード生成
        generator = FeedGenerator()
        try:
            feed = generator.generate_feed(url, config=feed_config)
        except (FeedGenerationError, ParseError) as e:
            click.echo(f"フィード生成エラー: {e}", err=True)
            sys.exit(1)
        
        # 出力
        xml_content = feed.to_xml()
        
        if output:
            # ファイル出力
            output_path = Path(output)
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(xml_content)
                click.echo(f"RSSフィードを出力しました: {output_path}")
            except IOError as e:
                click.echo(f"ファイル出力エラー: {e}", err=True)
                sys.exit(1)
        else:
            # 標準出力
            click.echo(xml_content)
    
    except Exception as e:
        click.echo(f"予期しないエラーが発生しました: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()