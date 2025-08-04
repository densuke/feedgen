"""Web API起動コマンド."""

import click
import uvicorn


@click.command()
@click.option("--host", default="127.0.0.1", help="バインドするホスト")
@click.option("--port", default=8000, help="バインドするポート")
@click.option("--reload", is_flag=True, help="開発モード（ファイル変更で自動リロード）")
def serve(host: str, port: int, reload: bool) -> None:
    """Web APIサーバーを起動.
    
    Args:
        host: バインドするホスト
        port: バインドするポート 
        reload: 開発モード
        
    """
    click.echo(f"feedgen Web API サーバーを起動します...")
    click.echo(f"URL: http://{host}:{port}")
    click.echo(f"API仕様書: http://{host}:{port}/docs")
    
    uvicorn.run(
        "feedgen.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    serve()