import pytest

from conftest import foremanctl_run, service_is_enabled, service_is_running

pytestmark = pytest.mark.iop


def test_gateway_service(server):
    assert service_is_running(server, "iop-core-gateway")
    assert service_is_enabled(server, "iop-core-gateway")


def test_gateway_port(server):
    result = foremanctl_run(server, "podman run --rm --network=foreman-proxy-net quay.io/centos/centos:stream9 bash -c 'echo > /dev/tcp/iop-core-gateway/8443'")
    assert result.rc == 0


def test_gateway_secrets(server):
    secrets = [
        'iop-core-gateway-server-cert',
        'iop-core-gateway-server-key',
        'iop-core-gateway-server-ca-cert',
        'iop-core-gateway-client-cert',
        'iop-core-gateway-client-key',
        'iop-core-gateway-client-ca-cert',
        'iop-core-gateway-relay-conf'
    ]

    result = foremanctl_run(server, "podman secret ls --format '{{.Name}}'")
    assert result.succeeded

    for secret_name in secrets:
        assert secret_name in result.stdout
