import json

import pytest

from conftest import foremanctl_run, service_exists, service_is_enabled, service_is_running

FOREMAN_HOST = 'localhost'
FOREMAN_PORT = 3000

RECURRING_INSTANCES = [
    "hourly",
    "daily",
    "weekly",
    "monthly",
]

@pytest.fixture(scope="module")
def foreman_status_curl(server):
    return server.run(f"curl --header 'X-FORWARDED-PROTO: https' --silent --write-out '%{{stderr}}%{{http_code}}' http://{FOREMAN_HOST}:{FOREMAN_PORT}/api/v2/ping")

@pytest.fixture(scope="module")
def foreman_status(foreman_status_curl):
    return json.loads(foreman_status_curl.stdout)


def test_foreman_service(server):
    assert service_is_running(server, "foreman")


def test_foreman_port(server):
    # Port 3000 is published to host loopback so httpd can proxy to Foreman
    foreman = server.addr(FOREMAN_HOST)
    assert foreman.port(FOREMAN_PORT).is_reachable


def test_foreman_status(foreman_status_curl):
    assert foreman_status_curl.succeeded
    assert foreman_status_curl.stderr == '200'


def test_foreman_status_database(foreman_status):
    assert foreman_status['results']['foreman']['database']['active']


def test_foreman_status_cache(foreman_status):
    assert foreman_status['results']['foreman']['cache']['servers']
    assert foreman_status['results']['foreman']['cache']['servers'][0]['status'] == 'ok'


@pytest.mark.parametrize("katello_service", ['candlepin', 'candlepin_auth', 'candlepin_events', 'foreman_tasks', 'katello_events', 'pulp3', 'pulp3_content'])
def test_katello_services_status(foreman_status, katello_service):
    assert foreman_status['results']['katello']['services'][katello_service]['status'] == 'ok'


@pytest.mark.parametrize("dynflow_instance", ['orchestrator', 'worker', 'worker-hosts-queue'])
def test_foreman_dynflow_container_instances(server, dynflow_instance):
    # Quadlet files are in the foremanctl user's config directory
    result = foremanctl_run(server, f"test -L ~/.config/containers/systemd/dynflow-sidekiq@{dynflow_instance}.container")
    assert result.succeeded


@pytest.mark.parametrize("dynflow_instance", ['orchestrator', 'worker', 'worker-hosts-queue'])
def test_foreman_dynflow_service_instances(server, dynflow_instance):
    assert service_is_running(server, f"dynflow-sidekiq@{dynflow_instance}")


@pytest.mark.parametrize("instance", RECURRING_INSTANCES)
def test_foreman_recurring_timers_enabled_and_running(server, instance):
    assert service_is_running(server, f"foreman-recurring@{instance}.timer")
    assert service_is_enabled(server, f"foreman-recurring@{instance}.timer")


@pytest.mark.parametrize("instance", RECURRING_INSTANCES)
def test_foreman_recurring_services_exist(server, instance):
    assert service_exists(server, f"foreman-recurring@{instance}.service")


def test_foreman_delivery_method_setting(foremanapi):
    delivery_method_setting = foremanapi.list('settings', search='name=delivery_method')
    assert delivery_method_setting[0]['value'] == 'smtp'
