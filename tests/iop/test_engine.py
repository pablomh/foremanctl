import pytest

from conftest import (
    SYSTEMCTL_USER,
    foremanctl_run,
    service_is_enabled,
    service_is_running,
)

pytestmark = pytest.mark.iop


def test_engine_service(server):
    assert service_is_running(server, "iop-core-engine")
    assert service_is_enabled(server, "iop-core-engine")


def test_engine_secret(server):
    result = foremanctl_run(server, "podman secret ls --format '{{.Name}}'")
    assert result.succeeded
    assert "iop-core-engine-config-yml" in result.stdout


def test_engine_config_content(server):
    result = foremanctl_run(server, "podman secret inspect iop-core-engine-config-yml --showsecret")
    assert result.succeeded

    config_data = result.stdout.strip()
    assert "insights.specs.default" in config_data
    assert "insights_kafka_service.rules" in config_data
    assert "iop-core-kafka:9092" in config_data


def test_engine_service_dependencies(server):
    result = server.run(f"{SYSTEMCTL_USER} show iop-core-engine --property=After")
    assert result.succeeded
    assert "iop-core-ingress.service" in result.stdout
    assert "iop-core-kafka.service" in result.stdout


def test_engine_kafka_connectivity(server):
    result = foremanctl_run(server, "podman logs iop-core-engine 2>&1 | grep -i 'kafka\\|bootstrap'")
    assert result.succeeded
