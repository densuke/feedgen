"""SSRF対策付き取得(safe_fetch)の仕様テスト.

仕様:
  - http/https 以外のスキームは拒否する
  - ホスト名が解決したアドレスが1つでも公開アドレスでなければ拒否する
    (プライベート, ループバック, リンクローカル, CGNAT, 予約, 未指定, マルチキャスト,
     IPv4射影IPv6)
  - リダイレクトは自動で追わず、遷移先ごとに同じ検査をかける(最大5回)
  - 拒否は UnsafeURLError (FeedGenerationError の子) で表す
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from feedgen.core import safe_fetch
from feedgen.core.exceptions import FeedGenerationError, UnsafeURLError
from feedgen.core.feed_detector import FeedDetector
from feedgen.core.parser import HTMLParser

PUBLIC_IP = "93.184.216.34"


def _resp(status=200, location=None, text="ok"):
    headers = {"Location": location} if location else {}
    return SimpleNamespace(status_code=status, headers=headers, text=text)


@pytest.fixture
def dns(monkeypatch):
    """ホスト名ごとの解決結果を差し替える."""
    table: dict[str, list[str]] = {}

    def resolve(host):
        return table[host]

    monkeypatch.setattr(safe_fetch, "resolve_host", resolve)
    return table


class TestUnsafeURLError:
    def test_is_a_feed_generation_error(self):
        assert issubclass(UnsafeURLError, FeedGenerationError)


class TestEnsurePublicUrlScheme:
    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "ftp://example.com/",
            "gopher://example.com/",
            "javascript:alert(1)",
            "//example.com/feed",
            "example.com/feed",
            "",
        ],
    )
    def test_rejects_non_http_schemes(self, url):
        with pytest.raises(UnsafeURLError):
            safe_fetch.ensure_public_url(url)

    def test_rejects_missing_host(self):
        with pytest.raises(UnsafeURLError):
            safe_fetch.ensure_public_url("http:///path")


class TestEnsurePublicUrlLiteralIp:
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/",
            "http://127.0.0.1:9998/",
            "http://10.0.0.1/",
            "http://172.16.0.1/",
            "http://192.168.1.1/",
            "http://169.254.169.254/computeMetadata/v1/",
            "http://100.64.0.1/",
            "http://0.0.0.0/",
            "http://224.0.0.1/",
            "http://240.0.0.1/",
            "http://[::1]/",
            "http://[fe80::1]/",
            "http://[fd7a:115c:a1e0::1]/",
            "http://[::ffff:127.0.0.1]/",
            "http://[::ffff:169.254.169.254]/",
        ],
    )
    def test_rejects_non_public_literal(self, url):
        with pytest.raises(UnsafeURLError):
            safe_fetch.ensure_public_url(url)

    @pytest.mark.parametrize(
        "url",
        ["http://93.184.216.34/", "https://8.8.8.8/feed", "http://[2606:4700:4700::1111]/"],
    )
    def test_accepts_public_literal(self, url):
        safe_fetch.ensure_public_url(url)


class TestEnsurePublicUrlHostname:
    def test_accepts_hostname_resolving_to_public(self, dns):
        dns["example.com"] = [PUBLIC_IP]
        safe_fetch.ensure_public_url("https://example.com/feed")

    @pytest.mark.parametrize("addr", ["127.0.0.1", "10.1.2.3", "169.254.169.254", "::1"])
    def test_rejects_hostname_resolving_to_non_public(self, dns, addr):
        dns["evil.example"] = [addr]
        with pytest.raises(UnsafeURLError):
            safe_fetch.ensure_public_url("https://evil.example/")

    def test_rejects_when_any_record_is_non_public(self, dns):
        dns["mixed.example"] = [PUBLIC_IP, "127.0.0.1"]
        with pytest.raises(UnsafeURLError):
            safe_fetch.ensure_public_url("https://mixed.example/")

    def test_rejects_unresolvable_host(self, monkeypatch):
        import socket

        def boom(host):
            raise socket.gaierror("no such host")

        monkeypatch.setattr(safe_fetch, "resolve_host", boom)
        with pytest.raises(UnsafeURLError):
            safe_fetch.ensure_public_url("https://nx.example/")

    def test_rejects_empty_resolution(self, dns):
        dns["empty.example"] = []
        with pytest.raises(UnsafeURLError):
            safe_fetch.ensure_public_url("https://empty.example/")

    def test_error_message_does_not_leak_resolved_address(self, dns):
        dns["evil.example"] = ["10.9.8.7"]
        with pytest.raises(UnsafeURLError) as exc:
            safe_fetch.ensure_public_url("https://evil.example/")
        assert "10.9.8.7" not in str(exc.value)


class TestSafeRequest:
    def test_returns_response_for_public_url(self, dns):
        dns["example.com"] = [PUBLIC_IP]
        with patch("feedgen.core.safe_fetch._http_get", return_value=_resp()) as get:
            response = safe_fetch.safe_request("get", "https://example.com/", timeout=5)
        assert response.status_code == 200
        _, kwargs = get.call_args
        assert "allow_redirects" not in kwargs
        assert kwargs["timeout"] == 5

    def test_applies_default_timeout(self, dns):
        dns["example.com"] = [PUBLIC_IP]
        with patch("feedgen.core.safe_fetch._http_get", return_value=_resp()) as get:
            safe_fetch.safe_request("get", "https://example.com/")
        assert get.call_args.kwargs["timeout"] == safe_fetch.DEFAULT_TIMEOUT

    def test_does_not_call_network_for_private_url(self):
        with patch("feedgen.core.safe_fetch._http_get") as get:
            with pytest.raises(UnsafeURLError):
                safe_fetch.safe_request("get", "http://127.0.0.1:9998/")
        get.assert_not_called()

    def test_ignores_caller_allow_redirects(self, dns):
        dns["example.com"] = [PUBLIC_IP]
        with patch("feedgen.core.safe_fetch._http_head", return_value=_resp()) as head:
            safe_fetch.safe_request("head", "https://example.com/", allow_redirects=True)
        assert "allow_redirects" not in head.call_args.kwargs

    def test_rejects_unknown_method(self):
        with pytest.raises(ValueError):
            safe_fetch.safe_request("delete", "https://example.com/")

    def test_follows_redirect_to_public_host(self, dns):
        dns["a.example"] = [PUBLIC_IP]
        dns["b.example"] = [PUBLIC_IP]
        responses = [_resp(302, "https://b.example/feed"), _resp(200, text="final")]
        with patch("feedgen.core.safe_fetch._http_get", side_effect=responses) as get:
            response = safe_fetch.safe_request("get", "https://a.example/")
        assert response.text == "final"
        assert get.call_args_list[1].args[0] == "https://b.example/feed"

    def test_resolves_relative_redirect(self, dns):
        dns["a.example"] = [PUBLIC_IP]
        responses = [_resp(301, "/new"), _resp(200)]
        with patch("feedgen.core.safe_fetch._http_get", side_effect=responses) as get:
            safe_fetch.safe_request("get", "https://a.example/old")
        assert get.call_args_list[1].args[0] == "https://a.example/new"

    @pytest.mark.parametrize(
        "target",
        [
            "http://127.0.0.1:9998/",
            "http://169.254.169.254/",
            "file:///etc/passwd",
            "http://[::1]/",
        ],
    )
    def test_rejects_redirect_to_non_public(self, dns, target):
        dns["a.example"] = [PUBLIC_IP]
        with patch("feedgen.core.safe_fetch._http_get", return_value=_resp(302, target)) as get:
            with pytest.raises(UnsafeURLError):
                safe_fetch.safe_request("get", "https://a.example/")
        assert get.call_count == 1

    def test_rejects_redirect_to_hostname_resolving_private(self, dns):
        dns["a.example"] = [PUBLIC_IP]
        dns["internal.example"] = ["10.0.0.5"]
        with patch(
            "feedgen.core.safe_fetch._http_get",
            return_value=_resp(302, "https://internal.example/"),
        ):
            with pytest.raises(UnsafeURLError):
                safe_fetch.safe_request("get", "https://a.example/")

    def test_rejects_too_many_redirects(self, dns):
        dns["a.example"] = [PUBLIC_IP]
        with patch(
            "feedgen.core.safe_fetch._http_get",
            return_value=_resp(302, "https://a.example/loop"),
        ) as get:
            with pytest.raises(UnsafeURLError):
                safe_fetch.safe_request("get", "https://a.example/")
        assert get.call_count == safe_fetch.MAX_REDIRECTS + 1

    def test_redirect_without_location_is_returned_as_is(self, dns):
        dns["a.example"] = [PUBLIC_IP]
        with patch("feedgen.core.safe_fetch._http_get", return_value=_resp(302)):
            response = safe_fetch.safe_request("get", "https://a.example/")
        assert response.status_code == 302


class TestIntegrationWithFetchers:
    """取得を行う各クラスが safe_fetch を経由することを確認する."""

    def test_html_parser_rejects_private_url(self):
        with patch("feedgen.core.safe_fetch._http_get") as get:
            with pytest.raises(UnsafeURLError):
                HTMLParser().fetch_content("http://127.0.0.1:9998/")
        get.assert_not_called()

    def test_feed_detector_fetch_feed_rejects_private_url(self):
        with patch("feedgen.core.safe_fetch._http_get") as get:
            with pytest.raises(UnsafeURLError):
                FeedDetector().fetch_feed("http://169.254.169.254/feed")
        get.assert_not_called()

    def test_feed_detector_detect_rejects_private_url(self):
        with patch("feedgen.core.safe_fetch._http_get") as get:
            with pytest.raises(FeedGenerationError):
                FeedDetector().detect_feeds("http://10.0.0.1/")
        get.assert_not_called()

    def test_check_feed_exists_treats_unsafe_redirect_as_missing(self, dns):
        dns["a.example"] = [PUBLIC_IP]
        with patch(
            "feedgen.core.safe_fetch._http_head",
            return_value=_resp(302, "http://127.0.0.1:9998/"),
        ):
            assert FeedDetector()._check_feed_exists("https://a.example/feed") is False
