def test_foreman_target(user_service):
    assert user_service("foreman.target").is_running
    assert user_service("foreman.target").is_enabled
