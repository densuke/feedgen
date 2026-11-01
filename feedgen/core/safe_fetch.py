"""SSRF対策付きのHTTP取得.

公開エンドポイントが利用者指定のURLを取得するため、内部アドレス(ループバック、
プライベート、リンクローカル、メタデータなど)への到達を防ぐ。

- http/https 以外は拒否する
- ホスト名が解決したアドレスが1つでも公開アドレスでなければ拒否する
- リダイレクトは自動で追わず、遷移先ごとに同じ検査をかける

残るリスク: 検査時と接続時で名前解決が変わる DNS リバインディングは防げない。
接続先アドレスの固定は Rust 版(Issue #877)で行う。
"""

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

from .exceptions import UnsafeURLError

MAX_REDIRECTS = 5

_ALLOWED_SCHEMES = {"http", "https"}
_REDIRECT_STATUS = {301, 302, 303, 307, 308}
_METHODS = {"get", "head"}


def resolve_host(host: str) -> list[str]:
    """ホスト名を解決し、アドレスの一覧を返す."""
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return sorted({info[4][0] for info in infos})


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def _addresses_of(host: str) -> list[str]:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return [host]
    try:
        return resolve_host(host)
    except socket.gaierror as e:
        raise UnsafeURLError("ホスト名を解決できません") from e


def ensure_public_url(url: str) -> None:
    """公開アドレスへのhttp/https URLでなければ UnsafeURLError を送出する."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeURLError("http または https の URL のみ取得できます")
    if not parsed.hostname:
        raise UnsafeURLError("URL にホストがありません")
    addresses = _addresses_of(parsed.hostname)
    if not addresses or not all(_is_public(a) for a in addresses):
        raise UnsafeURLError("このアドレスへのアクセスは許可されていません")


def safe_request(method: str, url: str, **kwargs) -> requests.Response:
    """検査付きで取得する。リダイレクトは遷移先ごとに再検査する."""
    if method not in _METHODS:
        raise ValueError(f"未対応のメソッドです: {method}")
    kwargs.pop("allow_redirects", None)
    send = getattr(requests, method)
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        ensure_public_url(current)
        response = send(current, allow_redirects=False, **kwargs)
        location = response.headers.get("Location")
        if response.status_code not in _REDIRECT_STATUS or not location:
            return response
        current = urljoin(current, location)
    raise UnsafeURLError("リダイレクトが多すぎます")
