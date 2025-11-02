"""CLIメイン機能."""

import os
import sys
from pathlib import Path

import click

from ..core import FeedGenerator, URLGenerator
from .config import ConfigManager
from ..core.exceptions import FeedGenerationError, ParseError


@click.command()
@click.argument("url")
@click.option("--config", "-c", help="設定ファイルのパス")
@click.option("--output", "-o", help="出力ファイルのパス")
@click.option("--max-items", type=int, help="最大記事数")
@click.option("--user-agent", help="User-Agentヘッダー")
@click.option("--use-feed", is_flag=True, help="既存フィードがある場合は代理取得")
@click.option("--feed-first", is_flag=True, help="フィード検出を優先（見つからない場合のみHTML解析）")
@click.option("--generate-url", is_flag=True, help="Web API用のURLを生成して出力")
@click.option("--api-host", help="Web APIのホスト名（--generate-urlと併用）")
@click.option("--decode-google-news", is_flag=True, help="Google News URLを実際の記事URLにデコード")
@click.option("--google-news-interval", type=int, help="Google Newsデコード処理の間隔（秒）")
@click.option("--google-news-timeout", type=int, help="Google Newsデコード処理のタイムアウト（秒）")
@click.option("--google-news-cache-ttl", type=int, help="Google Newsキャッシュ有効期限（秒）")
@click.option("--google-news-cache-type", type=click.Choice(['memory', 'redis']), help="Google Newsキャッシュタイプ")
@click.option("--google-news-cache-size", type=int, help="Google Newsメモリキャッシュサイズ")
def cli(url: str, config: str | None, output: str | None,
        max_items: int | None, user_agent: str | None,
        use_feed: bool, feed_first: bool, generate_url: bool, api_host: str | None,
        decode_google_news: bool, google_news_interval: int | None, google_news_timeout: int | None,
        google_news_cache_ttl: int | None, google_news_cache_type: str | None, google_news_cache_size: int | None) -> None:
    """指定されたURLからRSSフィードを生成またはWeb API URLを生成.
    
    Args:
        url: 分析対象のURL
        config: 設定ファイルのパス
        output: 出力ファイルのパス
        max_items: 最大記事数
        user_agent: User-Agentヘッダー
        use_feed: 既存フィードがある場合は代理取得
        feed_first: フィード検出を優先
        generate_url: Web API用のURLを生成
        api_host: Web APIのホスト名
        decode_google_news: Google News URLデコード有効化
        google_news_interval: Google Newsデコード処理間隔
        google_news_timeout: Google Newsデコード処理タイムアウト
        google_news_cache_ttl: Google Newsキャッシュ有効期限
        google_news_cache_type: Google Newsキャッシュタイプ
        google_news_cache_size: Google Newsメモリキャッシュサイズ

    """
    try:
        # 設定を読み込み
        config_manager = ConfigManager()
        
        # デフォルト設定を取得
        feed_config = config_manager.get_default_config()
        
        # 設定ファイルを判定（優先順位: --config > FEEDGEN_CONFIG > config.yaml/config.yml）
        config_candidates: list[Path] = []
        if config:
            config_candidates.append(Path(config))
        else:
            env_config = os.getenv("FEEDGEN_CONFIG")
            if env_config:
                config_candidates.append(Path(env_config))
            else:
                for candidate_name in ("config.yaml", "config.yml"):
                    candidate_path = Path(candidate_name)
                    if candidate_path.exists():
                        config_candidates.append(candidate_path)
                        break

        for config_path in config_candidates:
            try:
                file_config = config_manager.load_config(str(config_path))
                feed_config = config_manager.merge_configs(feed_config, file_config)
            except (FileNotFoundError, Exception) as e:
                click.echo(f"設定ファイル読み込みエラー: {e}", err=True)
                sys.exit(1)

        # コマンドライン引数で設定をオーバーライド
        if max_items is not None:
            feed_config["max_items"] = max_items
        if user_agent is not None:
            feed_config["user_agent"] = user_agent
        
        # Google News設定のオーバーライド
        if (decode_google_news or google_news_interval is not None or google_news_timeout is not None or
            google_news_cache_ttl is not None or google_news_cache_type is not None or google_news_cache_size is not None):
            google_news_config = feed_config.get("google_news", {})
            
            if decode_google_news:
                google_news_config["decode_enabled"] = True
            if google_news_interval is not None:
                google_news_config["request_interval"] = google_news_interval
            if google_news_timeout is not None:
                google_news_config["request_timeout"] = google_news_timeout
            if google_news_cache_ttl is not None:
                google_news_config["cache_ttl"] = google_news_cache_ttl
            if google_news_cache_type is not None:
                google_news_config["cache_type"] = google_news_cache_type
            if google_news_cache_size is not None:
                google_news_config["cache_max_size"] = google_news_cache_size
                
            feed_config["google_news"] = google_news_config

        # URL生成モード
        if generate_url:
            # APIホストを決定（優先順位: コマンドライン > 設定ファイル）
            api_base_url = api_host or feed_config.get("api_base_url")
            
            if not api_base_url:
                click.echo(
                    "エラー: APIホストが指定されていません。\n"
                    "--api-host オプションを使用するか、設定ファイルで api_base_url を設定してください。",
                    err=True
                )
                sys.exit(1)
            
            try:
                # ベースURLを正規化
                normalized_url = URLGenerator.normalize_base_url(api_base_url)
                url_generator = URLGenerator(normalized_url)
                
                # URLが有効かチェック
                if not url_generator.validate_base_url(normalized_url):
                    click.echo(f"エラー: 無効なAPIホストです: {api_base_url}", err=True)
                    sys.exit(1)
                
                # API URLを生成
                api_url = url_generator.generate_feed_url(
                    target_url=url,
                    max_items=max_items,
                    use_feed=use_feed if use_feed else None,
                    feed_first=feed_first if feed_first else None,
                    user_agent=user_agent,
                    decode_google_news=decode_google_news if decode_google_news else None,
                    google_news_interval=google_news_interval,
                    google_news_timeout=google_news_timeout,
                )
                
                # 出力
                if output:
                    # ファイル出力
                    output_path = Path(output)
                    try:
                        with open(output_path, "w", encoding="utf-8") as f:
                            f.write(api_url)
                        click.echo(f"API URLを出力しました: {output_path}")
                    except OSError as e:
                        click.echo(f"ファイル出力エラー: {e}", err=True)
                        sys.exit(1)
                else:
                    # 標準出力
                    click.echo(api_url)
                    
                return
                
            except Exception as e:
                click.echo(f"URL生成エラー: {e}", err=True)
                sys.exit(1)

        # フィード生成（従来の動作）
        # YouTube API Keyを設定ファイルから取得（メソッドが存在する場合）
        youtube_api_key = getattr(config_manager, 'get_youtube_api_key', lambda: None)()

        # Google News設定を取得
        google_news_config = config_manager.get_google_news_config(feed_config)

        # Instagram設定を取得
        instagram_config = feed_config.get("instagram", {})
        instagram_username = instagram_config.get("username") or os.getenv("INSTAGRAM_USERNAME")
        instagram_session_file = instagram_config.get("session_file") or os.getenv("INSTAGRAM_SESSION_FILE")
        instagram_max_posts = instagram_config.get("max_posts", 20)
        use_instagram_full_client = instagram_config.get("use_full_client", False)

        if instagram_username == "":
            instagram_username = None
        if instagram_session_file == "":
            instagram_session_file = None

        generator = FeedGenerator(
            youtube_api_key=youtube_api_key,
            google_news_config=google_news_config,
            instagram_username=instagram_username,
            instagram_session_file=instagram_session_file,
            instagram_max_posts=instagram_max_posts,
            use_instagram_full_client=use_instagram_full_client
        )

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
