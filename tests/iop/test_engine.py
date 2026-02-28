import pytest

from conftest import get_service


def test_engine_service(server, user):
    service = get_service(server, "iop-core-engine", user)
    assert service.is_running


def test_engine_secret(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman secret ls --format '{{{{.Name}}}}'")
    assert result.succeeded
    assert "iop-core-engine-config-yml" in result.stdout


def test_engine_config_content(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman secret inspect iop-core-engine-config-yml --showsecret")
    assert result.succeeded

    config_data = result.stdout.strip()
    assert "insights.specs.default" in config_data
    assert "insights_kafka_service.rules" in config_data
    assert "iop-core-kafka:9092" in config_data


def test_engine_service_dependencies(server, user):
    result = server.run(f"systemctl --machine={user}@ --user show iop-core-engine --property=After")
    assert result.succeeded
    assert "iop-core-ingress.service" in result.stdout
    assert "iop-core-kafka.service" in result.stdout


def test_engine_kafka_connectivity(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman logs iop-core-engine 2>&1 | grep -i 'kafka\\|bootstrap'")
    assert result.succeeded
