import pytest

from conftest import get_service


def test_yuptoo_service(server, user):
    service = get_service(server, "iop-core-yuptoo", user)
    assert service.is_running
