import pytest

from conftest import get_service


def test_remediation_api_service(server, user):
    service = get_service(server, "iop-service-remediations-api", user)
    assert service.is_running


def test_remediation_api_service_dependencies(server, user):
    result = server.run(f"systemctl --machine={user}@ --user show iop-service-remediations-api --property=After")
    assert result.succeeded
    assert "iop-core-host-inventory-api.service" in result.stdout
    assert "iop-service-advisor-backend-api.service" in result.stdout


def test_remediation_api_environment_variables(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman inspect iop-service-remediations-api --format '{{{{.Config.Env}}}}'")
    assert result.succeeded
    assert "REDIS_ENABLED=false" in result.stdout
    assert "RBAC_ENFORCE=false" in result.stdout
    assert "DB_SSL_ENABLED=false" in result.stdout


def test_remediation_api_endpoint(server, user):
    result = server.run("curl -s -o /dev/null -w '%{http_code}' http://localhost:9002/ 2>/dev/null || echo '000'")
    assert result.stdout.strip() != "000"
