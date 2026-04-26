import pytest

from conftest import (
    SYSTEMCTL_USER,
    foremanctl_run,
    service_is_enabled,
    service_is_running,
)

pytestmark = pytest.mark.iop


def test_remediation_api_service(server):
    assert service_is_running(server, "iop-service-remediations-api")
    assert service_is_enabled(server, "iop-service-remediations-api")


def test_remediation_api_service_dependencies(server):
    result = server.run(f"{SYSTEMCTL_USER} show iop-service-remediations-api --property=After")
    assert result.succeeded
    assert "iop-core-host-inventory-api.service" in result.stdout
    assert "iop-service-advisor-backend-api.service" in result.stdout


def test_remediation_api_environment_variables(server):
    result = foremanctl_run(server, "podman inspect iop-service-remediations-api --format '{{.Config.Env}}'")
    assert result.succeeded
    assert "REDIS_ENABLED=false" in result.stdout
    assert "RBAC_ENFORCE=false" in result.stdout
    assert "DB_SSL_ENABLED=false" in result.stdout


def test_remediation_api_endpoint(server):
    result = server.run("curl -s -o /dev/null -w '%{http_code}' http://localhost:9002/ 2>/dev/null || echo '000'")
    assert result.stdout.strip() != "000"
