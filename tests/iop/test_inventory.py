import pytest

from conftest import (
    SYSTEMCTL_USER,
    foremanctl_run,
    service_is_enabled,
    service_is_running,
)

pytestmark = pytest.mark.iop


def test_inventory_migrate_service(server):
    assert service_is_enabled(server, "iop-core-host-inventory-migrate")


def test_inventory_mq_service(server):
    assert service_is_running(server, "iop-core-host-inventory")
    assert service_is_enabled(server, "iop-core-host-inventory")


def test_inventory_api_service(server):
    assert service_is_running(server, "iop-core-host-inventory-api")
    assert service_is_enabled(server, "iop-core-host-inventory-api")


def test_inventory_service_dependencies(server):
    result = server.run(f"{SYSTEMCTL_USER} show iop-core-host-inventory --property=After")
    assert result.succeeded
    assert "iop-core-host-inventory-migrate.service" in result.stdout


def test_inventory_api_endpoint(server):
    result = foremanctl_run(server, "podman run --rm quay.io/iop/host-inventory:latest curl -s -o /dev/null -w '%{http_code}' http://iop-core-host-inventory-api:8081/health")
    if result.succeeded:
        assert "200" in result.stdout


def test_inventory_hosts_endpoint(server):
    result = foremanctl_run(server, "podman run --rm quay.io/iop/host-inventory:latest curl -s -o /dev/null -w '%{http_code}' http://iop-core-host-inventory-api:8081/api/inventory/v1/hosts")
    if result.succeeded:
        assert "200" in result.stdout


def test_inventory_cleanup_service(server):
    assert not service_is_running(server, "iop-core-host-inventory-cleanup")


def test_inventory_cleanup_service_enabled(server):
    result = server.run(f"{SYSTEMCTL_USER} is-enabled iop-core-host-inventory-cleanup")
    assert result.succeeded
    assert "generated" in result.stdout


def test_inventory_cleanup_timer(server):
    assert service_is_enabled(server, "iop-core-host-inventory-cleanup.timer")
    assert service_is_running(server, "iop-core-host-inventory-cleanup.timer")


def test_inventory_cleanup_timer_config(server):
    timer_file = server.file("/var/lib/foremanctl/.config/systemd/user/iop-core-host-inventory-cleanup.timer")
    assert timer_file.exists
    assert timer_file.is_file

    content = timer_file.content_string
    assert "OnBootSec=10min" in content
    assert "OnUnitActiveSec=24h" in content
    assert "Persistent=true" in content
    assert "RandomizedDelaySec=300" in content
    assert "WantedBy=timers.target" in content
