"""SSRF対策付きのHTTP取得.

公開エンドポイントが利用者指定のURLを取得するため、内部アドレス(ループバック、
プライベート、リンクローカル、メタデータなど)への到達を防ぐ。

- 検査するホストは、実際に接続する側(requests が使う urllib3)と同じパーサで決める。
  バックスラッシュ・制御文字・空白・userinfo を含むURLはパーサ間で解釈が割れるため拒否する
- http/https 以外は拒否する。名前解決したアドレスが1つでも公開でなければ拒否する
- リダイレクトは自動で追わず、遷移先ごとに同じ検査をかける
- TCP 接続の直後(TLS ハンドシェイクの前)に実際の接続先アドレスを検査する(検査後に
  名前解決が変わる DNS リバインディングを、何も送る前に止める)
- 応答本文は圧縮の前後とも MAX_BYTES まで。展開は上限つきで行う(圧縮爆弾の対策)。
  本文の読み取りには全体の締切を設ける。環境変数のプロキシ設定は読まない
"""

import ipaddress
import re
import socket
import time
import zlib
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.util import parse_url

from .exceptions import UnsafeURLError

MAX_REDIRECTS = 5
MAX_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT = 30
TOTAL_TIMEOUT = 45

_DENIED = "このアドレスへのアクセスは許可されていません"
_ALLOWED_SCHEMES = {"http", "https"}
_REDIRECT_STATUS = {301, 302, 303, 307, 308}
_METHODS = {"get", "head"}
_FORBIDDEN_CHARS = re.compile(r"[\x00-\x20\x7f\\]")
_NON_PUBLIC_V6 = [
    ipaddress.ip_network("::/96"),
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
    ipaddress.ip_network("::ffff:0:0:0/96"),
    ipaddress.ip_network("fec0::/10"),
]


def resolve_host(host: str) -> list[str]:
    """ホスト名を解決し、アドレスの一覧を返す."""
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return sorted({info[4][0] for info in infos})


def _is_public_v4(ip: ipaddress.IPv4Address) -> bool:
    return ip.is_global and not ip.is_multicast


def _is_public_v6(ip: ipaddress.IPv6Address) -> bool:
    if ip.ipv4_mapped is not None:
        return _is_public_v4(ip.ipv4_mapped)
    if ip.teredo is not None:
        return False
    if ip.sixtofour is not None:
        return _is_public_v4(ip.sixtofour)
    if any(ip in network for network in _NON_PUBLIC_V6):
        return False
    return ip.is_global and not ip.is_multicast


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address):
        return _is_public_v6(ip)
    return _is_public_v4(ip)


def _addresses_of(host: str) -> list[str]:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return [host]
    try:
        return resolve_host(host)
    except (OSError, UnicodeError) as e:
        raise UnsafeURLError(_DENIED) from e


def _bare(host: str | None) -> str:
    """比較用に、小文字化しゾーンID(%...)を除く."""
    return (host or "").lower().split("%")[0]


def _target_host(url: str) -> str:
    """requests が実際に接続するホストを返す。解釈が割れるURLは拒否する."""
    if _FORBIDDEN_CHARS.search(url):
        raise UnsafeURLError(_DENIED)
    try:
        parsed = urlparse(url)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            raise UnsafeURLError("http または https の URL のみ取得できます")
        if "@" in parsed.netloc:
            raise UnsafeURLError(_DENIED)
        sent_url = requests.Request("GET", url).prepare().url
        sent_host = parse_url(sent_url).hostname
        declared_host = parsed.hostname
    except (ValueError, requests.RequestException) as e:
        raise UnsafeURLError(_DENIED) from e
    if not sent_host:
        raise UnsafeURLError("URL にホストがありません")
    sent_host = sent_host.strip("[]")
    if url.isascii() and _bare(declared_host) != _bare(sent_host):
        raise UnsafeURLError(_DENIED)
    return sent_host


def ensure_public_url(url: str) -> None:
    """公開アドレスへのhttp/https URLでなければ UnsafeURLError を送出する."""
    addresses = _addresses_of(_target_host(url))
    if not addresses or not all(_is_public(a) for a in addresses):
        raise UnsafeURLError(_DENIED)


def _verify_peer(sock) -> None:
    """接続済みソケットの相手が公開アドレスでなければ、送信前に切断して拒否する."""
    if not _is_public(sock.getpeername()[0]):
        sock.close()
        raise UnsafeURLError(_DENIED)


class _GuardedHTTPConnection(HTTPConnection):
    def _new_conn(self):
        sock = super()._new_conn()
        _verify_peer(sock)
        return sock


class _GuardedHTTPSConnection(HTTPSConnection):
    def _new_conn(self):
        sock = super()._new_conn()
        _verify_peer(sock)
        return sock


class _GuardedHTTPPool(HTTPConnectionPool):
    ConnectionCls = _GuardedHTTPConnection


class _GuardedHTTPSPool(HTTPSConnectionPool):
    ConnectionCls = _GuardedHTTPSConnection


class _GuardedAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {
            "http": _GuardedHTTPPool,
            "https": _GuardedHTTPSPool,
        }


def _new_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.headers["Accept-Encoding"] = "identity"
    adapter = _GuardedAdapter()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _decode_limited(data: bytes, encoding: str) -> bytes:
    """圧縮された本文を、展開後も MAX_BYTES を超えない範囲でだけ展開する."""
    if encoding in ("", "identity"):
        return data
    if encoding not in ("gzip", "x-gzip", "deflate"):
        raise UnsafeURLError("未対応の圧縮形式です")
    last_error: Exception | None = None
    for wbits in (47, -15) if encoding == "deflate" else (47,):
        decoder = zlib.decompressobj(wbits)
        try:
            out = decoder.decompress(data, MAX_BYTES + 1)
            if len(out) > MAX_BYTES or decoder.unconsumed_tail:
                raise UnsafeURLError("応答が大きすぎます")
            out += decoder.flush()
        except zlib.error as e:
            last_error = e
            continue
        if len(out) > MAX_BYTES:
            raise UnsafeURLError("応答が大きすぎます")
        return out
    raise UnsafeURLError("応答を展開できません") from last_error


def _read_limited(response: requests.Response, budget: float) -> None:
    """本文を MAX_BYTES まで、budget 秒以内に読み込む."""
    declared = response.headers.get("Content-Length", "")
    if declared.isascii() and declared.isdigit() and int(declared) > MAX_BYTES:
        response.close()
        raise UnsafeURLError("応答が大きすぎます")
    deadline = time.monotonic() + budget
    chunks: list[bytes] = []
    size = 0
    while True:
        if time.monotonic() > deadline:
            response.close()
            raise UnsafeURLError("応答に時間がかかりすぎています")
        chunk = response.raw.read1(65536, decode_content=False)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_BYTES:
            response.close()
            raise UnsafeURLError("応答が大きすぎます")
        chunks.append(chunk)
    encoding = response.headers.get("Content-Encoding", "").strip().lower()
    try:
        response._content = _decode_limited(b"".join(chunks), encoding)
    finally:
        response.close()


def _budget(timeout) -> float:
    """requests の timeout(数値または組)から、本文読み取りの持ち時間を決める."""
    if isinstance(timeout, tuple):
        return float(max(t for t in timeout if t is not None))
    return float(timeout)


def _clamp(timeout, remaining: float):
    """timeout を、全体の残り時間を超えない値にする."""
    if isinstance(timeout, tuple):
        return tuple(None if t is None else min(t, remaining) for t in timeout)
    return min(timeout, remaining)


def _fetch(method: str, url: str, **kwargs) -> requests.Response:
    timeout = kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    with _new_session() as session:
        response = session.request(method, url, allow_redirects=False, stream=True, **kwargs)
        if method == "GET" and response.status_code not in _REDIRECT_STATUS:
            _read_limited(response, _budget(timeout))
        else:
            response.close()
        return response


def _http_get(url: str, **kwargs) -> requests.Response:
    return _fetch("GET", url, **kwargs)


def _http_head(url: str, **kwargs) -> requests.Response:
    return _fetch("HEAD", url, **kwargs)


def safe_request(method: str, url: str, **kwargs) -> requests.Response:
    """検査付きで取得する。リダイレクトは遷移先ごとに再検査する."""
    if method not in _METHODS:
        raise ValueError(f"未対応のメソッドです: {method}")
    kwargs.pop("allow_redirects", None)
    timeout = kwargs.pop("timeout", DEFAULT_TIMEOUT)
    deadline = time.monotonic() + TOTAL_TIMEOUT
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise UnsafeURLError("応答に時間がかかりすぎています")
        ensure_public_url(current)
        send = {"get": _http_get, "head": _http_head}[method]
        response = send(current, timeout=_clamp(timeout, remaining), **kwargs)
        location = response.headers.get("Location")
        if response.status_code not in _REDIRECT_STATUS or not location:
            return response
        close = getattr(response, "close", None)
        if close is not None:
            close()
        current = urljoin(current, location)
    raise UnsafeURLError("リダイレクトが多すぎます")
