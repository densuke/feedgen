"""CLIメイン機能."""

import sys
from pathlib import Path

import click

from ..core import FeedGenerator
from ..core.exceptions import FeedGenerationError, ParseError
from .config import ConfigManager


@click.command()
@click.argument("url")
@click.option("--config", "-c", help="設定ファイルのパス")
@click.option("--output", "-o", help="出力ファイルのパス")
@click.option("--max-items", type=int, help="最大記事数")
@click.option("--user-agent", help="User-Agentヘッダー")
@click.option("--use-feed", is_flag=True, help="既存フィードがある場合は代理取得")
@click.option("--feed-first", is_flag=True, help="フィード検出を優先（見つからない場合のみHTML解析）")
def cli(url: str, config: str | None, output: str | None,
        max_items: int | None, user_agent: str | None,
        use_feed: bool, feed_first: bool) -> None:
    """指定されたURLからRSSフィードを生成.
    
    Args:
        url: 分析対象のURL
        config: 設定ファイルのパス
        output: 出力ファイルのパス
        max_items: 最大記事数
        user_agent: User-Agentヘッダー
        use_feed: 既存フィードがある場合は代理取得
        feed_first: フィード検出を優先

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
            feed_config["max_items"] = max_items
        if user_agent is not None:
            feed_config["user_agent"] = user_agent

        # フィード生成
        generator = FeedGenerator()

        # フィード検出を行う
        if use_feed or feed_first:
            try:
                existing_feeds = generator.detect_existing_feeds(url)

                if existing_feeds:
                    if use_feed:
                        # 代理取得モード
                        feed_info = existing_feeds[0]  # 最初に見つかったフィードを使用
                        click.echo(f"既存フィードを発見: {feed_info['title']} ({feed_info['type']})")
                        click.echo(f"フィードURL: {feed_info['url']}")

                        xml_content, content_type = generator.fetch_existing_feed(feed_info["url"])
                        click.echo("既存フィードを代理取得しました。")
                    else:
                        # 通知モード（feed_first=True）
                        feed_info = existing_feeds[0]
                        click.echo(f"既存フィードが見つかりました: {feed_info['title']} ({feed_info['type']})", err=True)
                        click.echo(f"フィードURL: {feed_info['url']}", err=True)
                        click.echo("--use-feedオプションで代理取得できます。", err=True)
                        click.echo("HTML解析を継続します...", err=True)

                        # HTML解析を実行
                        feed = generator.generate_feed(url, config=feed_config)
                        xml_content = feed.to_xml()
                else:
                    # フィードが見つからない場合はHTML解析
                    if feed_first:
                        click.echo("既存フィードが見つかりませんでした。HTML解析を実行します。", err=True)

                    feed = generator.generate_feed(url, config=feed_config)
                    xml_content = feed.to_xml()

            except (FeedGenerationError, ParseError) as e:
                click.echo(f"フィード処理エラー: {e}", err=True)
                sys.exit(1)
        else:
            # 通常のHTML解析モード
            try:
                feed = generator.generate_feed(url, config=feed_config)
                xml_content = feed.to_xml()
            except (FeedGenerationError, ParseError) as e:
                click.echo(f"フィード生成エラー: {e}", err=True)
                sys.exit(1)

        if output:
            # ファイル出力
            output_path = Path(output)
            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(xml_content)
                click.echo(f"RSSフィードを出力しました: {output_path}")
            except OSError as e:
                click.echo(f"ファイル出力エラー: {e}", err=True)
                sys.exit(1)
        else:
            # 標準出力
            click.echo(xml_content)

    except Exception as e:
        click.echo(f"予期しないエラーが発生しました: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
