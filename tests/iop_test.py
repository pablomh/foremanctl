"""Tests for the IoP (Insights on Premises) deployment.

Covers:
- All IOP containers running under the foremanctl user
- iop-core-network exists in the foremanctl Podman namespace
- IOP gateway reachable from foreman-proxy-net (via container DNS, not host port)
- Network isolation: IOP containers cannot reach the public internet
"""

import pytest

from conftest import foremanctl_exec, foremanctl_run, service_is_running

IOP_SERVICES = [
    "iop-core-kafka",
    "iop-core-ingress",
    "iop-core-puptoo",
    "iop-core-yuptoo",
    "iop-core-engine",
    "iop-core-gateway",
    "iop-core-host-inventory",
    "iop-service-advisor-backend-api",
    "iop-service-vmaas-reposcan",
    "iop-service-vulnerability-manager",
    "iop-service-remediations-api",
]


@pytest.fixture(scope="module")
def iop_enabled(server):
    """Skip all IOP tests if the iop feature is not enabled."""
    result = foremanctl_run(server, "systemctl --user is-active iop-core-kafka 2>/dev/null || true")
    if result.rc != 0:
        pytest.skip("IOP feature not enabled or not deployed")


def test_iop_network_exists(server, iop_enabled):
    result = foremanctl_run(server, "podman network ls --format '{{.Name}}'")
    assert result.succeeded
    assert "iop-core-network" in result.stdout


@pytest.mark.parametrize("service", IOP_SERVICES)
def test_iop_service_running(server, iop_enabled, service):
    assert service_is_running(server, service), f"{service} is not running"


def test_iop_gateway_on_proxy_net(server, iop_enabled):
    # The gateway must be reachable by name on foreman-proxy-net.
    # Verify it is connected to both expected networks.
    result = foremanctl_run(server, "podman inspect iop-core-gateway --format '{{json .NetworkSettings.Networks}}'")
    assert result.succeeded
    assert "iop-core-network" in result.stdout
    assert "foreman-proxy-net" in result.stdout


def test_iop_gateway_no_host_port(server, iop_enabled):
    # The gateway must NOT publish any host ports — it is accessed via foreman-proxy-net.
    result = foremanctl_run(server, "podman port iop-core-gateway")
    # podman port prints nothing (exits 0) when no ports are published
    assert result.succeeded
    assert result.stdout.strip() == ""


def test_iop_network_isolation(server, iop_enabled):
    # Containers on iop-core-network (internal=true) must not reach the public internet.
    result = foremanctl_exec(server, "iop-core-kafka",
                             "bash -c 'curl --max-time 3 --silent https://example.com; echo $?'")
    # curl exits non-zero (6 = cannot resolve host, 28 = timeout) for an isolated network
    assert result.stdout.strip() != "0", "IOP container should not reach the public internet"


def test_kafka_topics_exist(server, iop_enabled):
    result = foremanctl_exec(server, "iop-core-kafka",
                             "bash -c './bin/kafka-topics.sh --bootstrap-server iop-core-kafka:9092 --list'")
    assert result.succeeded
    assert "platform.inventory.events" in result.stdout
    assert "platform.engine.results" in result.stdout


def test_iop_gateway_registered_in_foreman(server, iop_enabled, foremanapi):
    # The IOP gateway must be registered as a smart proxy named 'iop-gateway'.
    # Foreman reaches it via container DNS on foreman-proxy-net at port 8443.
    proxies = foremanapi.list('smart_proxies', search='name=iop-gateway')
    assert len(proxies) == 1, "iop-gateway smart proxy not registered in Foreman"
    assert "8443" in proxies[0]['url'], \
        f"Expected gateway URL with port 8443, got: {proxies[0]['url']}"


def test_iop_postgresql_socket_accessible(server, iop_enabled):
    # IOP containers must be able to connect to PostgreSQL via the Unix socket.
    result = foremanctl_exec(server, "iop-core-host-inventory",
                             "bash -c 'psql -U inventory_admin -h /var/run/postgresql -c \"SELECT 1\" inventory_db'")
    assert result.succeeded
