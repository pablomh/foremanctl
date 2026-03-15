from conftest import foremanctl_run


def test_redis_service(user_service):
    assert user_service("redis").is_running


def test_redis_ping(server):
    result = foremanctl_run(server, "podman exec redis redis-cli ping")
    assert result.succeeded
    assert result.stdout.strip() == "PONG"
