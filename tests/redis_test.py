from conftest import container_exec, service_is_running


def test_redis_service(server):
    assert service_is_running(server, "redis")


def test_redis_ping(server):
    result = container_exec(server, "redis", "valkey-cli ping")
    assert result.succeeded
    assert result.stdout.strip() == "PONG"
