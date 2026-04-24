import json

from conftest import container_exec, foremanctl_run, service_is_running

FOREMAN_PROXY_PORT = 8443

def test_foreman_proxy_service(server):
    assert service_is_running(server, "foreman-proxy")

def test_foreman_proxy_port(server):
    # Port 8443 is published externally so managed hosts can reach the smart proxy
    assert server.addr('localhost').port(FOREMAN_PROXY_PORT).is_reachable

def test_foreman_proxy_etc_hosts_debug(server, server_fqdn):
    hosts_content = container_exec(server, "foreman-proxy", "cat /etc/hosts")
    print(f"DEBUG HOSTS: proxy /etc/hosts content:\n{hosts_content.stdout}")
    hostname = container_exec(server, "foreman-proxy", "hostname -f")
    print(f"DEBUG HOSTS: proxy hostname: {hostname.stdout.strip()}")
    self_resolve = container_exec(server, "foreman-proxy", f"getent hosts {hostname.stdout.strip()}")
    print(f"DEBUG HOSTS: self-resolution rc={self_resolve.rc} stdout={self_resolve.stdout.strip()}")
    fqdn_resolve = container_exec(server, "foreman-proxy", f"getent hosts {server_fqdn}")
    print(f"DEBUG HOSTS: fqdn resolution rc={fqdn_resolve.rc} stdout={fqdn_resolve.stdout.strip()}")
    host_etc_hosts = server.run("cat /etc/hosts")
    print(f"DEBUG HOSTS: host /etc/hosts:\n{host_etc_hosts.stdout}")
    inspect = foremanctl_run(server, "podman inspect foreman-proxy --format '{{.HostConfig.Binds}}'")
    print(f"DEBUG HOSTS: container binds: {inspect.stdout.strip()}")

def test_foreman_proxy_features(server, certificates, server_fqdn):
    cmd = server.run(f"curl --cacert {certificates['ca_certificate']} --silent https://{server_fqdn}:{FOREMAN_PROXY_PORT}/features")
    assert cmd.succeeded
    features = json.loads(cmd.stdout)
    assert "logs" in features
    assert "script" in features
    assert "dynflow" in features
