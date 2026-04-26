import pytest

from conftest import service_is_enabled, service_is_running

pytestmark = pytest.mark.iop


def test_puptoo_service(server):
    assert service_is_running(server, "iop-core-puptoo")
    assert service_is_enabled(server, "iop-core-puptoo")
