import pytest

from conftest import (
    SYSTEMCTL_USER,
    foremanctl_run,
    service_is_enabled,
    service_is_running,
)

pytestmark = pytest.mark.iop


def test_vmaas_reposcan_service(server):
    assert service_is_running(server, "iop-service-vmaas-reposcan")
    assert service_is_enabled(server, "iop-service-vmaas-reposcan")


def test_vmaas_webapp_go_service(server):
    assert service_is_running(server, "iop-service-vmaas-webapp-go")
    assert service_is_enabled(server, "iop-service-vmaas-webapp-go")


def test_vmaas_webapp_go_service_dependencies(server):
    result = server.run(f"{SYSTEMCTL_USER} show iop-service-vmaas-webapp-go --property=After")
    assert result.succeeded
    assert "iop-service-vmaas-reposcan.service" in result.stdout


def test_vmaas_webapp_go_service_wants(server):
    result = server.run(f"{SYSTEMCTL_USER} show iop-service-vmaas-webapp-go --property=Wants")
    assert result.succeeded
    assert "iop-service-vmaas-reposcan.service" in result.stdout


def test_vmaas_database_secrets(server):
    result = foremanctl_run(server, "podman secret ls --format '{{.Name}}'")
    assert result.succeeded
    assert "iop-service-vmaas-reposcan-database-username" in result.stdout
    assert "iop-service-vmaas-reposcan-database-password" in result.stdout
    assert "iop-service-vmaas-reposcan-database-name" in result.stdout
    assert "iop-service-vmaas-reposcan-database-host" in result.stdout
    assert "iop-service-vmaas-reposcan-database-port" in result.stdout


def test_vmaas_data_volume(server):
    result = foremanctl_run(server, "podman volume ls --format '{{.Name}}' | grep iop-service-vmaas-data")
    assert result.succeeded
    assert "iop-service-vmaas-data" in result.stdout
