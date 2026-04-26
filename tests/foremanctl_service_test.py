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
    # List long-running services in foreman.target and check each is active.
    # Timer-triggered .service units (foreman-recurring@*) are oneshot and
    # inactive between triggers, so exclude them.
    result = server.run(f"{SYSTEMCTL_USER} list-dependencies --plain foreman.target")
    assert result.succeeded
    services = [
        s.strip() for s in result.stdout.splitlines()
        if s.strip()
        and s.strip() != "foreman.target"
        and ".timer" not in s
        and "recurring" not in s
    ]
    assert len(services) > 0
    for svc in services:
        assert service_is_running(server, svc), f"{svc} is not running"


def test_foremanctl_service_ps(server):
    result = server.run(f"{SYSTEMD_RUN} -- podman ps")
    assert result.succeeded
    assert "foreman" in result.stdout


def test_foremanctl_service_exec(server):
    result = container_exec(server, "foreman", "echo hello")
    assert result.succeeded
    assert "hello" in result.stdout
