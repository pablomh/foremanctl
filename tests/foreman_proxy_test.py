import json

from conftest import service_is_running

FOREMAN_PROXY_PORT = 8443

def test_foreman_proxy_service(server):
    assert service_is_running(server, "foreman-proxy")

def test_foreman_proxy_port(server):
    # Port 8443 is published externally so managed hosts can reach the smart proxy
    assert server.addr('localhost').port(FOREMAN_PROXY_PORT).is_reachable

def test_foreman_proxy_features(server, certificates, server_fqdn):
    cmd = server.run(f"curl --cacert {certificates['ca_certificate']} --silent https://{server_fqdn}:{FOREMAN_PROXY_PORT}/features")
    assert cmd.succeeded
    features = json.loads(cmd.stdout)
    assert "logs" in features
    assert "script" in features
    assert "dynflow" in features
