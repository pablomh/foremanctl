import time

CURL_CMD = "curl --silent --output /dev/null"
FOREMAN_PING_RETRIES = 60
FOREMAN_PING_DELAY = 10


def _wait_for_foreman(server, server_fqdn, certificates):
    """Poll the Foreman HTTPS frontend until available or timeout."""
    for _ in range(FOREMAN_PING_RETRIES):
        cmd = server.run(
            f"{CURL_CMD} --cacert {certificates['ca_certificate']}"
            f" --write-out '%{{http_code}}' https://{server_fqdn}/api/v2/ping"
        )
        if cmd.stdout == '200':
            return
        time.sleep(FOREMAN_PING_DELAY)
    units = server.run("systemctl --machine=foremanctl@ --user list-units --all --no-pager --no-legend")
    status = server.run("systemctl --machine=foremanctl@ --user status foreman.service --no-pager -l")
    containers = server.run("runuser -l foremanctl -s /bin/bash -c 'XDG_RUNTIME_DIR=/run/user/$(id -u) podman ps -a --format \"{{.Names}} {{.Status}}\"'")
    logs = server.run("runuser -l foremanctl -s /bin/bash -c 'XDG_RUNTIME_DIR=/run/user/$(id -u) podman logs --tail 50 foreman 2>&1'")
    raise AssertionError(
        f"Foreman did not become available after target lifecycle operation\n"
        f"Service states:\n{units.stdout}\n"
        f"foreman.service status:\n{status.stdout}\n"
        f"Container states:\n{containers.stdout}\n"
        f"Foreman container logs:\n{logs.stdout}"
    )


def test_foreman_target_stop_start(server, user_service, server_fqdn, certificates):
    result = server.run("systemctl --machine=foremanctl@ --user stop foreman.target")
    assert result.rc == 0, f"Failed to stop foreman.target: {result.stderr}"
    assert not user_service("foreman.target").is_running

    result = server.run("systemctl --machine=foremanctl@ --user start foreman.target")
    assert result.rc == 0, f"Failed to start foreman.target: {result.stderr}"
    _wait_for_foreman(server, server_fqdn, certificates)
    assert user_service("foreman.target").is_running


def test_foreman_target_restart(server, user_service, server_fqdn, certificates):
    result = server.run("systemctl --machine=foremanctl@ --user restart foreman.target")
    assert result.rc == 0, f"Failed to restart foreman.target: {result.stderr}"
    _wait_for_foreman(server, server_fqdn, certificates)
    assert user_service("foreman.target").is_running
