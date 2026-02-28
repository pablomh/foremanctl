import pytest

from conftest import get_service


def test_vmaas_reposcan_service(server, user):
    service = get_service(server, "iop-service-vmaas-reposcan", user)
    assert service.is_running


def test_vmaas_webapp_go_service(server, user):
    service = get_service(server, "iop-service-vmaas-webapp-go", user)
    assert service.is_running


def test_vmaas_webapp_go_service_dependencies(server, user):
    result = server.run(f"systemctl --machine={user}@ --user show iop-service-vmaas-webapp-go --property=After")
    assert result.succeeded
    assert "iop-service-vmaas-reposcan.service" in result.stdout


def test_vmaas_webapp_go_service_wants(server, user):
    result = server.run(f"systemctl --machine={user}@ --user show iop-service-vmaas-webapp-go --property=Wants")
    assert result.succeeded
    assert "iop-service-vmaas-reposcan.service" in result.stdout


def test_vmaas_database_secrets(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman secret ls --format '{{{{.Name}}}}'")
    assert result.succeeded
    assert "iop-service-vmaas-reposcan-database-username" in result.stdout
    assert "iop-service-vmaas-reposcan-database-password" in result.stdout
    assert "iop-service-vmaas-reposcan-database-name" in result.stdout
    assert "iop-service-vmaas-reposcan-database-host" in result.stdout
    assert "iop-service-vmaas-reposcan-database-port" in result.stdout


def test_vmaas_data_volume(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman volume ls --format '{{{{.Name}}}}' | grep iop-service-vmaas-data")
    assert result.succeeded
    assert "iop-service-vmaas-data" in result.stdout
