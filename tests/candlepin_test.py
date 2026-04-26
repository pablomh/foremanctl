from conftest import container_exec, foremanctl_run, service_is_running


def assert_secret_content(server, secret_name, secret_value):
    # Secrets live in the foremanctl user's Podman store
    secret = foremanctl_run(server, f'podman secret inspect --format {{{{.SecretData}}}} --showsecret {secret_name}')
    assert secret.succeeded
    assert secret.stdout.strip() == secret_value


def test_candlepin_service(server):
    assert service_is_running(server, "candlepin")


def test_candlepin_port(server):
    # Port 23443 is published to host loopback for httpd proxy access
    assert server.addr("localhost").port("23443").is_reachable


def test_candlepin_status(server, certificates):
    # Use --resolve so curl verifies against the 'candlepin' SAN on the cert
    # while connecting to the host-published port on 127.0.0.1.
    status = server.run(f"curl --resolve candlepin:23443:127.0.0.1 --cacert {certificates['ca_certificate']} --silent --output /dev/null --write-out '%{{http_code}}' https://candlepin:23443/candlepin/status")
    assert status.succeeded
    assert status.stdout == '200'


def test_tls(server):
    result = server.run('nmap --script +ssl-enum-ciphers localhost -p 23443')
    result = result.stdout
    # We don't enable TLSv1.3 by default yet. TLSv1.3 support was added in tomcat 7.0.92
    # But tomcat 7.0.76 is the latest version available on EL7
    assert "TLSv1.3" not in result

    # Test that TLSv1.2 is enabled
    assert "TLSv1.2" in result

    # Test that older TLS versions are disabled
    assert "TLSv1.1" not in result
    assert "TLSv1.0" not in result

    # Test that the least cipher strength is "strong" or "A"
    assert "least strength: A" in result
