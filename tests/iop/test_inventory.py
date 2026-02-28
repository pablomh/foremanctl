import pytest

from conftest import get_service, get_user_home


def test_inventory_migrate_service(server, user):
    service = get_service(server, "iop-core-host-inventory-migrate", user)
    assert service.is_running


def test_inventory_mq_service(server, user):
    service = get_service(server, "iop-core-host-inventory", user)
    assert service.is_running


def test_inventory_api_service(server, user):
    service = get_service(server, "iop-core-host-inventory-api", user)
    assert service.is_running


def test_inventory_service_dependencies(server, user):
    result = server.run(f"systemctl --machine={user}@ --user show iop-core-host-inventory --property=After")
    assert result.succeeded
    assert "iop-core-host-inventory-migrate.service" in result.stdout


def test_inventory_api_endpoint(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman run --rm quay.io/iop/host-inventory:latest curl -s -o /dev/null -w '%{{http_code}}' http://iop-core-host-inventory-api:8081/health")
    if result.succeeded:
        assert "200" in result.stdout


def test_inventory_hosts_endpoint(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman run --rm quay.io/iop/host-inventory:latest curl -s -o /dev/null -w '%{{http_code}}' http://iop-core-host-inventory-api:8081/api/inventory/v1/hosts")
    if result.succeeded:
        assert "200" in result.stdout


def test_inventory_cleanup_service(server, user):
    user_home = get_user_home(server, user)
    container_file = server.file(f"{user_home}/.config/containers/systemd/iop-core-host-inventory-cleanup.container")
    assert container_file.exists
    assert container_file.is_file
    # Cleanup is a oneshot job triggered by timer, not running continuously
    service = get_service(server, "iop-core-host-inventory-cleanup", user)
    assert not service.is_running


def test_inventory_cleanup_service_enabled(server, user):
    service = get_service(server, "iop-core-host-inventory-cleanup", user)
    assert service.is_enabled


def test_inventory_cleanup_timer(server, user):
    timer = get_service(server, "iop-core-host-inventory-cleanup.timer", user)
    assert timer.is_running


def test_inventory_cleanup_timer_config(server, user):
    user_home = get_user_home(server, user)
    timer_file = server.file(f"{user_home}/.config/systemd/user/iop-core-host-inventory-cleanup.timer")
    assert timer_file.exists
    assert timer_file.is_file

    content = timer_file.content_string
    assert "OnBootSec=10min" in content
    assert "OnUnitActiveSec=24h" in content
    assert "Persistent=true" in content
    assert "RandomizedDelaySec=300" in content
    assert "WantedBy=timers.target" in content
