import time

from conftest import service_is_running, service_start, service_stop, service_restart

FOREMAN_PING_RETRIES = 60
FOREMAN_PING_DELAY = 10
CURL_CMD = "curl --silent --output /dev/null"


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
    raise AssertionError("Foreman did not become available after target lifecycle operation")


def test_foreman_target_stop_start(server, server_fqdn, certificates):
    result = service_stop(server, "foreman.target")
    assert result.rc == 0, f"Failed to stop foreman.target: {result.stderr}"
    assert not service_is_running(server, "foreman.target")

    result = service_start(server, "foreman.target")
    assert result.rc == 0, f"Failed to start foreman.target: {result.stderr}"
    _wait_for_foreman(server, server_fqdn, certificates)
    assert service_is_running(server, "foreman.target")


def test_foreman_target_restart(server, server_fqdn, certificates):
    result = service_restart(server, "foreman.target")
    assert result.rc == 0, f"Failed to restart foreman.target: {result.stderr}"
    _wait_for_foreman(server, server_fqdn, certificates)
    assert service_is_running(server, "foreman.target")
