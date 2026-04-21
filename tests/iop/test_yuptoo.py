import pytest

from conftest import service_is_enabled, service_is_running

pytestmark = pytest.mark.iop


def test_yuptoo_service(server):
    assert service_is_running(server, "iop-core-yuptoo")
    assert service_is_enabled(server, "iop-core-yuptoo")
