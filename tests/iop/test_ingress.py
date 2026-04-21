import pytest

from conftest import foremanctl_run, service_is_enabled, service_is_running

pytestmark = pytest.mark.iop


def test_ingress_service(server):
    assert service_is_running(server, "iop-core-ingress")
    assert service_is_enabled(server, "iop-core-ingress")


def test_ingress_http_endpoint(server):
    result = foremanctl_run(server, "podman run --rm quay.io/iop/ingress:latest curl -s -o /dev/null -w '%{http_code}' http://iop-core-ingress:8080/")
    if result.succeeded:
        assert "200" in result.stdout
