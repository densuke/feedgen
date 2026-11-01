"""safe_fetch の追加防御の仕様テスト.

仕様:
  - 検査するホストと、実際に接続するホストは同じパーサで決める。
    バックスラッシュ・制御文字・空白・userinfo(@)を含むURLは拒否する
  - IPv6 の NAT64・IPv4互換・6to4・Teredo は、埋め込みIPv4も含めて判定する
  - 名前解決の失敗と非公開アドレスは同じ文言で拒否する(内部名の列挙を防ぐ)
  - 接続した直後に実際の接続先アドレスを検査する(DNSリバインディング対策)
  - 応答本文は MAX_BYTES を超えたら拒否する。環境変数のプロキシ設定は読まない
"""

import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from feedgen.core import safe_fetch
from feedgen.core.exceptions import UnsafeURLError


def _resp(status=200, location=None):
    headers = {"Location": location} if location else {}
    return SimpleNamespace(status_code=status, headers=headers, text="")


class TestUrlParserDifferential:
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1\\@8.8.8.8/",
            "http://169.254.169.254\\@example.com/",
            "http://127.0.0.1:6379\\@example.com/",
            "http://example.com\\@127.0.0.1/",
            "http://example.com\\.evil.example/",
            "http://user@93.184.216.34/",
            "http://user:pw@example.com/",
            "http://exa mple.com/",
            "http://example.com/\nHost: evil",
            "http://example.com/\tx",
            "http://example.com/\x00",
            "http://example.com/\x7f",
        ],
    )
    def test_rejects_ambiguous_urls(self, url):
        with pytest.raises(UnsafeURLError):
            safe_fetch.ensure_public_url(url)

    def test_rejects_redirect_with_ambiguous_location(self):
        with patch(
            "feedgen.core.safe_fetch._http_get",
            return_value=_resp(302, "http://127.0.0.1\\@8.8.8.8/"),
        ) as get:
            with pytest.raises(UnsafeURLError):
                safe_fetch.safe_request("get", "https://a.example/")
        assert get.call_count == 1

    @pytest.mark.parametrize("url", ["https://bücher.example/feed", "https://日本語.example/"])
    def test_accepts_internationalized_host(self, url):
        safe_fetch.ensure_public_url(url)


class TestIpv6Embedded:
    @pytest.mark.parametrize(
        "url",
        [
            "http://[::127.0.0.1]/",
            "http://[::7f00:1]/",
            "http://[64:ff9b::7f00:1]/",
            "http://[64:ff9b::a9fe:a9fe]/",
            "http://[2002:7f00:1::1]/",
            "http://[2002:a9fe:a9fe::1]/",
            "http://[2001:0:4136:e378:8000:63bf:3fff:fdd2]/",
        ],
    )
    def test_rejects_embedded_internal_ipv4(self, url):
        with pytest.raises(UnsafeURLError):
            safe_fetch.ensure_public_url(url)

    def test_accepts_public_ipv6(self):
        safe_fetch.ensure_public_url("http://[2606:4700:4700::1111]/")


class TestUniformMessages:
    def test_unresolvable_and_private_share_one_message(self, monkeypatch):
        def gaierror(host):
            raise socket.gaierror("no such host")

        monkeypatch.setattr(safe_fetch, "resolve_host", gaierror)
        with pytest.raises(UnsafeURLError) as unresolved:
            safe_fetch.ensure_public_url("https://nx.example/")

        monkeypatch.setattr(safe_fetch, "resolve_host", lambda host: ["10.0.0.5"])
        with pytest.raises(UnsafeURLError) as private:
            safe_fetch.ensure_public_url("https://internal.example/")

        assert str(unresolved.value) == str(private.value)

    def test_overlong_label_is_rejected_not_crashing(self, monkeypatch):
        def bad_label(host):
            raise UnicodeError("label empty or too long")

        monkeypatch.setattr(safe_fetch, "resolve_host", bad_label)
        with pytest.raises(UnsafeURLError):
            safe_fetch.ensure_public_url("https://" + "a" * 70 + ".example/")


class _Handler(BaseHTTPRequestHandler):
    hits: list[str] = []
    body = b"hello"

    def do_GET(self):
        type(self).hits.append(self.path)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(type(self).body)))
        self.end_headers()
        self.wfile.write(type(self).body)

    def log_message(self, *args):
        pass


@pytest.fixture
def local_server():
    handler = type("H", (_Handler,), {"hits": [], "body": b"hello"})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield SimpleNamespace(port=server.server_address[1], handler=handler)
    server.shutdown()
    server.server_close()


class TestConnectionTimeGuard:
    """名前の検査を通っても、実際の接続先が内部なら送信前に拒否する."""

    def test_blocks_loopback_even_if_name_check_passes(self, local_server):
        # conftest が全ホスト名を公開IPへ解決させる=検査は通る。実接続は 127.0.0.1
        url = f"http://localhost:{local_server.port}/secret"
        safe_fetch.ensure_public_url(url)
        with pytest.raises(UnsafeURLError):
            safe_fetch.safe_request("get", url, timeout=5)
        assert local_server.handler.hits == []

    def test_allows_connection_when_peer_is_public(self, local_server, monkeypatch):
        monkeypatch.setattr(safe_fetch, "_is_public", lambda address: True)
        url = f"http://localhost:{local_server.port}/ok"
        response = safe_fetch.safe_request("get", url, timeout=5)
        assert response.text == "hello"
        assert local_server.handler.hits == ["/ok"]


class TestResponseLimits:
    def test_rejects_body_over_limit(self, local_server, monkeypatch):
        monkeypatch.setattr(safe_fetch, "_is_public", lambda address: True)
        monkeypatch.setattr(safe_fetch, "MAX_BYTES", 1024)
        local_server.handler.body = b"x" * 5000
        with pytest.raises(UnsafeURLError):
            safe_fetch.safe_request("get", f"http://localhost:{local_server.port}/big", timeout=5)

    def test_accepts_body_within_limit(self, local_server, monkeypatch):
        monkeypatch.setattr(safe_fetch, "_is_public", lambda address: True)
        monkeypatch.setattr(safe_fetch, "MAX_BYTES", 1024)
        local_server.handler.body = b"y" * 1000
        response = safe_fetch.safe_request(
            "get", f"http://localhost:{local_server.port}/ok", timeout=5
        )
        assert len(response.text) == 1000


class TestSessionSettings:
    def test_ignores_proxy_environment(self, monkeypatch):
        monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:3128")
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
        session = safe_fetch._new_session()
        assert session.trust_env is False
        assert session.proxies == {}
