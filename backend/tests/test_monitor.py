from unittest.mock import Mock

import pytest

from app import monitor


@pytest.mark.parametrize("failed", [False, True])
def test_monitor_independent_of_user_traffic(settings, repo, monkeypatch, failed):
    gauges = {}
    telemetry = Mock()
    telemetry.meter.create_gauge.side_effect = lambda name: gauges.setdefault(name, Mock())
    if failed:
        repo.health = Mock(side_effect=RuntimeError("no connection"))
    monkeypatch.setattr(monitor, "Settings", lambda: settings)
    monkeypatch.setattr(monitor, "Telemetry", lambda *args: telemetry)
    monkeypatch.setattr(monitor, "SnowflakeRepository", lambda *args: repo)
    assert monitor.main() == int(failed)
    assert gauges["omniclaim_data_dependency_up"].set.call_args.args[0] == int(not failed)
    assert telemetry.meter_provider.force_flush.called and telemetry.close.called
    if not failed:
        assert (
            gauges["omniclaim_published_as_of_timestamp_seconds"].set.call_args.args[0]
            == repo.as_of.timestamp()
        )
        assert gauges["omniclaim_monitor_last_success_timestamp_seconds"].set.called
