import pytest

from conftest import get_service


def test_puptoo_service(server, user):
    service = get_service(server, "iop-core-puptoo", user)
    assert service.is_running
