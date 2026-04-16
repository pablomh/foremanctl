"""Tests for the `foremanctl service` operational subcommand.

These tests exercise the tool itself rather than the underlying services,
ensuring that the tool correctly dispatches to the right systemd scope
and produces usable output for sysadmins.
"""

from conftest import service_is_running


def test_foremanctl_service_help(server):
    result = server.run("foremanctl service help")
    assert result.succeeded
    assert "status" in result.stdout
    assert "start" in result.stdout
    assert "stop" in result.stdout
    assert "restart" in result.stdout
    assert "logs" in result.stdout
    assert "ps" in result.stdout
    assert "exec" in result.stdout


def test_foremanctl_service_status_target(server):
    assert service_is_running(server, "foreman.target")


def test_foremanctl_service_status_brief(server):
    result = server.run("foremanctl service status -b")
    assert result.succeeded
    # All lines should show OK; no service should be failing
    assert "FAIL" not in result.stdout
    assert "OK" in result.stdout


def test_foremanctl_service_status_brief_order(server):
    result = server.run("foremanctl service status -b")
    assert result.succeeded
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    service_names = [l.split()[0] for l in lines]
    # foreman must appear after postgresql and redis (it depends on them)
    assert "foreman.service" in service_names or "foreman" in service_names
    assert "postgresql.service" in service_names or "postgresql" in service_names
    foreman_idx = next(i for i, n in enumerate(service_names) if "foreman" in n and "dynflow" not in n and "recurring" not in n and "proxy" not in n)
    postgresql_idx = next(i for i, n in enumerate(service_names) if "postgresql" in n)
    assert postgresql_idx < foreman_idx, "postgresql should start before foreman"


def test_foremanctl_service_ps(server):
    result = server.run("foremanctl service ps")
    assert result.succeeded
    # At least the foreman container should be listed
    assert "foreman" in result.stdout


def test_foremanctl_service_unknown_subcommand(server):
    result = server.run("foremanctl service does-not-exist")
    assert result.rc != 0
    assert "unknown subcommand" in result.stderr


def test_foremanctl_service_exec(server):
    # Verify exec works by running a trivial command in the foreman container
    result = server.run("foremanctl service exec foreman echo hello")
    assert result.succeeded
    assert "hello" in result.stdout
