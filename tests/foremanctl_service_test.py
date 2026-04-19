"""Tests for rootless service management.

Verifies that service operations work correctly in the foremanctl user
scope using the same systemd-native mechanisms as foremanctl-service.
"""

from conftest import (
    SYSTEMCTL_USER, SYSTEMD_RUN,
    container_exec, service_is_running,
)


def test_foremanctl_service_status_target(server):
    assert service_is_running(server, "foreman.target")


def test_foremanctl_service_status_brief(server):
    # List all services in foreman.target and check each is active
    result = server.run(f"{SYSTEMCTL_USER} list-dependencies --plain foreman.target")
    assert result.succeeded
    services = [s.strip() for s in result.stdout.splitlines() if s.strip() and s.strip() != "foreman.target"]
    assert len(services) > 0
    for svc in services:
        assert service_is_running(server, svc), f"{svc} is not running"


def test_foremanctl_service_status_brief_order(server):
    # systemctl list-dependencies traverses depth-first: leaf services
    # (postgresql, redis) appear before dependent ones (foreman)
    result = server.run(f"{SYSTEMCTL_USER} list-dependencies --plain foreman.target")
    assert result.succeeded
    services = [s.strip() for s in result.stdout.splitlines() if s.strip() and s.strip() != "foreman.target"]
    foreman_idx = next(i for i, n in enumerate(services) if "foreman" in n and "dynflow" not in n and "recurring" not in n and "proxy" not in n)
    postgresql_idx = next(i for i, n in enumerate(services) if "postgresql" in n)
    assert postgresql_idx < foreman_idx, "postgresql should start before foreman"


def test_foremanctl_service_ps(server):
    result = server.run(f"{SYSTEMD_RUN} -- podman ps")
    assert result.succeeded
    assert "foreman" in result.stdout


def test_foremanctl_service_exec(server):
    result = container_exec(server, "foreman", "echo hello")
    assert result.succeeded
    assert "hello" in result.stdout
