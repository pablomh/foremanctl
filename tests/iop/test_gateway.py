import pytest

from conftest import get_service


def test_gateway_service(server, user):
    service = get_service(server, "iop-core-gateway", user)
    assert service.is_running


def test_gateway_port(server, user):
    addr = server.addr("localhost")
    assert addr.port("24443").is_reachable


def test_gateway_secrets(server, user):
    secrets = [
        'iop-core-gateway-server-cert',
        'iop-core-gateway-server-key',
        'iop-core-gateway-server-ca-cert',
        'iop-core-gateway-client-cert',
        'iop-core-gateway-client-key',
        'iop-core-gateway-client-ca-cert',
        'iop-core-gateway-relay-conf'
    ]

    result = server.run(f"cd /tmp && sudo -u {user} podman secret ls --format '{{{{.Name}}}}'")
    assert result.succeeded

    for secret_name in secrets:
        assert secret_name in result.stdout
