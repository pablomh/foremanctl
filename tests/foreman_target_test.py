def test_foreman_target(user_service):
    foreman_target = user_service("foreman.target")
    assert foreman_target.is_running
    assert foreman_target.is_enabled
