"""テスト共通の設定."""

import pytest

PUBLIC_IP = "93.184.216.34"


@pytest.fixture(autouse=True)
def _resolve_hosts_offline(monkeypatch):
    """名前解決を実ネットワークに依存させない(全ホストを公開アドレスへ解決する)."""
    monkeypatch.setattr("feedgen.core.safe_fetch.resolve_host", lambda host: [PUBLIC_IP])
