import datetime
import json

import pytest

from tests.conftest import FOREMAN_PROXY_PORT
from tests.conftest import assert_container_resolves_server_fqdn


@pytest.fixture(scope="module")
def proxy_v2_features(curl_request, proxy_base_url):
    cmd = curl_request("v2/features", base_url=proxy_base_url, return_body=True)
    assert cmd.succeeded, f"Failed to query /v2/features: {cmd.stderr}"
    return json.loads(cmd.stdout)


@pytest.fixture(scope="module")
def expected_proxy_registration_url(obsah_params, server_fqdn):
    return obsah_params.get('foreman_proxy_registration_url', f'https://{server_fqdn}:{FOREMAN_PROXY_PORT}')


def test_foreman_proxy_features(curl_request, proxy_base_url, enabled_features):
    cmd = curl_request("features", base_url=proxy_base_url, return_body=True)
    assert cmd.succeeded
    features = json.loads(cmd.stdout)
    assert "logs" in features
    if 'remote-execution' in enabled_features:
        assert "script" in features
        assert "dynflow" in features
    else:
        assert "script" not in features
    if 'bmc' in enabled_features:
        assert "bmc" in features
    else:
        assert "bmc" not in features
    if 'templates' in enabled_features:
        assert "templates" in features
    else:
        assert "templates" not in features
    if 'ansible' in enabled_features:
        assert "ansible" in features
    else:
        assert "ansible" not in features
    if 'registration' in enabled_features:
        assert "registration" in features
        assert "templates" in features
    else:
        assert "registration" not in features


def test_foreman_proxy_service(server):
    foreman_proxy = server.service("foreman-proxy")
    assert foreman_proxy.is_running


def test_foreman_proxy_port(server):
    foreman_proxy = server.addr('localhost')
    assert foreman_proxy.port(FOREMAN_PROXY_PORT).is_reachable


@pytest.mark.feature('foreman')
def test_foreman_reaches_proxy_via_registration_url(server, expected_proxy_registration_url):
    cmd = server.run(
        "podman exec foreman curl "
        "--silent --show-error --fail "
        "--connect-timeout 5 --max-time 10 "
        "--cacert /etc/foreman/katello-default-ca.crt "
        "--cert /etc/foreman/client_cert.pem "
        "--key /etc/foreman/client_key.pem "
        f"{expected_proxy_registration_url}/v2/features"
    )
    assert cmd.succeeded, (
        "Foreman container could not reach the proxy via the registered "
        f"registration URL: {cmd.stderr}"
    )


@pytest.mark.feature('foreman')
def test_foreman_registers_proxy_with_public_fqdn_and_registration_url(server, certificates, server_fqdn, expected_proxy_registration_url):
    cmd = server.run(
        "curl --silent --show-error --fail "
        f"--cacert {certificates['server_ca_certificate']} "
        "--user admin:changeme "
        f"'https://{server_fqdn}/api/v2/smart_proxies?search=name=%22{server_fqdn}%22'"
    )
    assert cmd.succeeded, f"Failed to query smart proxy registration: {cmd.stderr}"

    smart_proxies = json.loads(cmd.stdout).get("results", [])
    smart_proxy = next((proxy for proxy in smart_proxies if proxy["name"] == server_fqdn), None)

    assert smart_proxy is not None, f"Smart proxy {server_fqdn} was not registered"
    assert smart_proxy["url"] == expected_proxy_registration_url


def test_foreman_proxy_resolves_server_fqdn(server, server_fqdn):
    assert_container_resolves_server_fqdn(server, "foreman-proxy", server_fqdn)


@pytest.mark.xfail(reason='Fails until report feature is available')
def test_foreman_proxy_client_auth_to_foreman(curl_request):
    test_report = {"config_report": {"host": "test.example.com", "reported_at": datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}}
    cmd = curl_request(
        "api/v2/config_reports",
        method="POST",
        data=json.dumps(test_report),
        headers={"Content-Type": "application/json"},
    )
    assert cmd.succeeded
    assert cmd.stdout == '201'


@pytest.mark.feature('bmc')
def test_bmc_capabilities(proxy_v2_features):
    assert 'bmc' in proxy_v2_features
    capabilities = proxy_v2_features['bmc'].get('capabilities', [])
    assert 'ipmitool' in capabilities
    assert 'freeipmi' in capabilities
    assert 'redfish' in capabilities


@pytest.mark.feature('bmc')
def test_bmc_default_provider(proxy_v2_features):
    settings = proxy_v2_features['bmc'].get('settings', {})
    assert settings.get('bmc_default_provider') == 'ipmitool'


@pytest.mark.feature('templates')
def test_templates_fetch_template_url(proxy_v2_features, obsah_params):
    assert 'templates' in proxy_v2_features
    settings = proxy_v2_features['templates'].get('settings', {})
    assert settings.get('template_url') == obsah_params.get('foreman_proxy_templates_url')


@pytest.mark.feature('templates')
def test_templates_endpoint_responds(curl_request, proxy_base_url, server_fqdn):
    """Fetch templateServer data from the templates proxy endpoint"""
    cmd = curl_request("unattended/templateServer", base_url=proxy_base_url, return_body=True)
    assert cmd.succeeded, f"Failed to query /unattended/templateServer: {cmd.stderr}"
    data = json.loads(cmd.stdout)
    assert 'templateServer' in data
    assert server_fqdn in data['templateServer']


@pytest.mark.feature('registration')
def test_registration_url(server, expected_proxy_registration_url):
    registration_config = server.file('/etc/foreman-proxy/settings.d/registration.yml')
    assert registration_config.exists
    assert registration_config.contains(expected_proxy_registration_url)


@pytest.mark.feature('registration')
def test_registration_endpoint(proxy_v2_features):
    assert 'registration' in proxy_v2_features
    assert proxy_v2_features['registration'].get('state') == 'running'
