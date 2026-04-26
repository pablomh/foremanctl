from conftest import service_is_enabled, service_is_running


def test_foreman_target(server):
    assert service_is_running(server, "foreman.target")
    assert service_is_enabled(server, "foreman.target")
