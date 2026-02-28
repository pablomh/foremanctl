import pytest

from conftest import get_service


def test_ingress_service(server, user):
    service = get_service(server, "iop-core-ingress", user)
    assert service.is_running


def test_ingress_http_endpoint(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman run --rm quay.io/iop/ingress:latest curl -s -o /dev/null -w '%{{http_code}}' http://iop-core-ingress:8080/")
    if result.succeeded:
        assert "200" in result.stdout
