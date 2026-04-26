import json

FOREMAN_PROXY_PORT = 8443

def test_foreman_proxy_features(server, certificates, server_fqdn):
    cmd = server.run(f"curl --cacert {certificates['ca_certificate']} --silent https://{server_fqdn}:{FOREMAN_PROXY_PORT}/features")
    assert cmd.succeeded
    features = json.loads(cmd.stdout)
    assert "logs" in features
    assert "script" in features
    assert "dynflow" in features

def test_foreman_proxy_service(server):
    foreman_proxy = server.service("foreman-proxy")
    assert foreman_proxy.is_running

def test_foreman_proxy_port(server):
    foreman_proxy = server.addr('localhost')
    assert foreman_proxy.port(FOREMAN_PROXY_PORT).is_reachable

def test_foreman_proxy_resolves_etc_hosts(server, server_fqdn):
    dns_result = server.run(f"podman exec foreman-proxy getent hosts {server_fqdn}")
    assert dns_result.rc == 0, f"DNS-resolvable host {server_fqdn} not found from proxy container"

    fake_host = "foremanctl-etc-hosts-test.example.com"
    fake_ip = "192.168.254.254"
    server.run(f"bash -c 'echo \"{fake_ip} {fake_host}\" >> /etc/hosts'")
    try:
        result = server.run(f"podman exec foreman-proxy getent hosts {fake_host}")
        assert result.rc == 0, f"/etc/hosts entry not resolvable from proxy container: {result.stderr}"
        assert fake_ip in result.stdout
    finally:
        server.run(f"sed -i '/{fake_host}/d' /etc/hosts")
