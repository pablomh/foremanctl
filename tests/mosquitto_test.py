def test_mosquitto_service(server):
    service = server.service("mosquitto")
    assert service.is_running

def test_mosquitto_port(server):
    assert server.addr('localhost').port(1883).is_reachable
