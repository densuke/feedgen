"""safe_fetch の資源上限・接続前検査の仕様テスト(再レビュー指摘への対応).

仕様:
  - 接続先の検査は TCP 接続の直後、TLS ハンドシェイクの前に行う(HTTPS でも ClientHello を送らない)
  - 圧縮応答は圧縮前後とも MAX_BYTES で打ち切る(展開は上限つきで行い、圧縮爆弾を防ぐ)。
    要求側は Accept-Encoding: identity を送る
  - 応答の本文読み取りには全体の締切を設ける(1バイトずつ返す遅い相手を保持し続けない)
  - 取得失敗の文言に接続先の詳細を含めない(内部ポートの開閉を区別させない)
  - Content-Length が数字でない場合も例外を漏らさない
"""

import gzip
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from feedgen.api.main import _redact
from feedgen.core import safe_fetch
from feedgen.core.exceptions import FeedGenerationError, UnsafeURLError
from feedgen.core.parser import HTMLParser


@pytest.fixture
def allow_loopback(monkeypatch):
    """ループバックの検査だけを外し、本物のHTTPサーバーに接続できるようにする."""
    monkeypatch.setattr(safe_fetch, "_is_public", lambda address: True)


def _serve(handler_cls):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class TestVerifyBeforeTls:
    def test_https_to_loopback_sends_no_bytes(self):
        received: list[bytes] = []
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def accept():
            listener.settimeout(3)
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            conn.settimeout(1)
            try:
                received.append(conn.recv(4096))
            except OSError:
                received.append(b"")
            conn.close()

        thread = threading.Thread(target=accept)
        thread.start()
        try:
            with pytest.raises(UnsafeURLError):
                safe_fetch.safe_request("get", f"https://localhost:{port}/", timeout=3)
        finally:
            thread.join()
            listener.close()
        assert received in ([], [b""])


class TestGenericFailureMessage:
    def test_connection_failure_hides_target_details(self):
        # 閉じたポート。conftest により名前検査は通り、実接続は拒否される
        with pytest.raises(FeedGenerationError) as exc:
            HTMLParser().fetch_content("http://localhost:1/")
        message = str(exc.value)
        assert "localhost" not in message
        assert "Max retries" not in message
        assert "Connection" not in message


class TestCompression:
    def test_requests_identity_encoding(self, allow_loopback):
        seen = []

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.headers.get("Accept-Encoding"))
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *args):
                pass

        server = _serve(H)
        try:
            safe_fetch.safe_request("get", f"http://localhost:{server.server_address[1]}/", timeout=5)
        finally:
            server.shutdown()
        assert seen == ["identity"]

    def test_gzip_bomb_is_rejected(self, allow_loopback, monkeypatch):
        monkeypatch.setattr(safe_fetch, "MAX_BYTES", 1024 * 1024)
        bomb = gzip.compress(b"\0" * (50 * 1024 * 1024))

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Content-Length", str(len(bomb)))
                self.end_headers()
                self.wfile.write(bomb)

            def log_message(self, *args):
                pass

        server = _serve(H)
        try:
            with pytest.raises(UnsafeURLError):
                safe_fetch.safe_request(
                    "get", f"http://localhost:{server.server_address[1]}/", timeout=10
                )
        finally:
            server.shutdown()

    def test_small_gzip_is_decoded(self, allow_loopback):
        payload = gzip.compress(b"hello gzip")

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        server = _serve(H)
        try:
            response = safe_fetch.safe_request(
                "get", f"http://localhost:{server.server_address[1]}/", timeout=5
            )
        finally:
            server.shutdown()
        assert response.text == "hello gzip"

    def test_unsupported_encoding_is_rejected(self):
        with pytest.raises(UnsafeURLError):
            safe_fetch._decode_limited(b"data", "br")

    def test_decode_limited_rejects_bomb_and_accepts_small(self, monkeypatch):
        monkeypatch.setattr(safe_fetch, "MAX_BYTES", 1000)
        with pytest.raises(UnsafeURLError):
            safe_fetch._decode_limited(gzip.compress(b"\0" * 100_000), "gzip")
        assert safe_fetch._decode_limited(gzip.compress(b"abc"), "gzip") == b"abc"
        assert safe_fetch._decode_limited(b"plain", "identity") == b"plain"

    def test_chunked_response_is_read(self, allow_loopback):
        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):
                self.send_response(200)
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                for part in (b"hel", b"lo"):
                    self.wfile.write(f"{len(part):x}\r\n".encode() + part + b"\r\n")
                self.wfile.write(b"0\r\n\r\n")

            def log_message(self, *args):
                pass

        server = _serve(H)
        try:
            response = safe_fetch.safe_request(
                "get", f"http://localhost:{server.server_address[1]}/", timeout=5
            )
        finally:
            server.shutdown()
        assert response.text == "hello"


class TestBodyDeadline:
    def test_slow_drip_response_is_cut_off(self, allow_loopback):
        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", "100")
                self.end_headers()
                try:
                    for _ in range(100):
                        self.wfile.write(b"x")
                        self.wfile.flush()
                        time.sleep(0.3)
                except OSError:
                    pass

            def log_message(self, *args):
                pass

        server = _serve(H)
        started = time.monotonic()
        try:
            with pytest.raises(UnsafeURLError):
                safe_fetch.safe_request(
                    "get", f"http://localhost:{server.server_address[1]}/", timeout=1.5
                )
        finally:
            server.shutdown()
        assert time.monotonic() - started < 6


class TestContentLengthParsing:
    class _Raw:
        def __init__(self, *chunks):
            self._chunks = list(chunks)

        def read1(self, amt=None, decode_content=None):
            return self._chunks.pop(0) if self._chunks else b""

    def test_non_ascii_digit_does_not_raise_value_error(self):
        response = SimpleNamespace(
            headers={"Content-Length": "²"}, raw=self._Raw(b"hello"), close=lambda: None
        )
        safe_fetch._read_limited(response, budget=5)
        assert response._content == b"hello"

    def test_declared_length_over_limit_is_rejected(self, monkeypatch):
        monkeypatch.setattr(safe_fetch, "MAX_BYTES", 10)
        response = SimpleNamespace(
            headers={"Content-Length": "11"}, raw=self._Raw(b"x"), close=lambda: None
        )
        with pytest.raises(UnsafeURLError):
            safe_fetch._read_limited(response, budget=5)


class TestMoreNonPublicAddresses:
    @pytest.mark.parametrize("url", ["http://[::ffff:0:7f00:1]/", "http://[fec0::1]/"])
    def test_rejects(self, url):
        with pytest.raises(UnsafeURLError):
            safe_fetch.ensure_public_url(url)


class TestRedact:
    @pytest.mark.parametrize(
        "text",
        [
            "key=SECRETVAL",
            "youtube_api_key=SECRETVAL",
            "client_secret=SECRETVAL",
            "refresh_token=SECRETVAL",
            "x-goog-api-key=SECRETVAL",
            "https://x.example/?q=1&key%3DSECRETVAL",
            "password=SECRETVAL&a=1",
        ],
    )
    def test_secret_values_are_hidden(self, text):
        assert "SECRETVAL" not in _redact(text)

    def test_plain_text_is_kept(self):
        assert _redact("フィード取得に失敗しました") == "フィード取得に失敗しました"
