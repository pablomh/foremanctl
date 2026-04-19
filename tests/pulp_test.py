import json
import pytest

from conftest import container_exec, foremanctl_run, service_is_enabled, service_is_running

PULP_HOST = 'localhost'
PULP_API_PORT = 24817
PULP_CONTENT_PORT = 24816

@pytest.fixture(scope="module")
def pulp_status_curl(server):
    return server.run(f"curl -k -s -w '%{{stderr}}%{{http_code}}' http://{PULP_HOST}:{PULP_API_PORT}/pulp/api/v3/status/")

@pytest.fixture(scope="module")
def pulp_status(pulp_status_curl):
    return json.loads(pulp_status_curl.stdout)

def test_pulp_api_service(server):
    assert service_is_running(server, "pulp-api")

def test_pulp_content_service(server):
    assert service_is_running(server, "pulp-content")

def test_pulp_worker_services(server):
    result = foremanctl_run(server, "systemctl --user list-units --all --type=service --no-legend 'pulp-worker@*.service' | awk '{print $1}'")
    worker_services = [s.strip() for s in result.stdout.split('\n') if s.strip()]
    assert len(worker_services) > 0

    for worker_service in worker_services:
        assert service_is_running(server, worker_service), f"{worker_service} is not running"

def test_pulp_api_port(server):
    # Port 24817 is published to host loopback for httpd proxy access
    assert server.addr(PULP_HOST).port(PULP_API_PORT).is_reachable

def test_pulp_content_port(server):
    # Port 24816 is published to host loopback for httpd proxy access
    assert server.addr(PULP_HOST).port(PULP_CONTENT_PORT).is_reachable

def test_pulp_status(pulp_status_curl):
    assert pulp_status_curl.succeeded
    assert pulp_status_curl.stderr == '200'

def test_pulp_status_database_connection(pulp_status):
    assert pulp_status['database_connection']['connected']


def test_pulp_status_redis_connection(pulp_status):
    assert pulp_status['redis_connection']['connected']


def test_pulp_status_api(pulp_status):
    assert pulp_status['online_api_apps']


def test_pulp_status_content(pulp_status):
    assert pulp_status['online_content_apps']


def test_pulp_status_workers(pulp_status):
    assert pulp_status['online_workers']


def test_pulp_volumes(server):
    assert server.file("/var/lib/pulp").is_directory

def test_pulp_worker_target(server):
    assert service_is_running(server, "pulp-worker.target")
    assert service_is_enabled(server, "pulp-worker.target")

def test_pulp_manager_check(server):
    result = container_exec(server, "pulp-api", "pulpcore-manager check --deploy")
    assert result.succeeded
