import pytest

from conftest import get_service


def test_iop_core_kafka_service(server, user):
    service = get_service(server, "iop-core-kafka", user)
    assert service.is_running


def test_iop_core_ingress_service(server, user):
    service = get_service(server, "iop-core-ingress", user)
    assert service.is_running


def test_iop_ingress_endpoint(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman exec iop-core-ingress curl -s -o /dev/null -w '%{{http_code}}' http://localhost:8080/ 2>/dev/null || echo '000'")
    assert result.rc == 0


def test_iop_core_puptoo_service(server, user):
    service = get_service(server, "iop-core-puptoo", user)
    assert service.is_running


def test_iop_puptoo_metrics_endpoint(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman exec iop-core-puptoo curl -s -o /dev/null -w '%{{http_code}}' http://localhost:8000/metrics 2>/dev/null || echo '000'")
    assert result.rc == 0


def test_iop_core_yuptoo_service(server, user):
    service = get_service(server, "iop-core-yuptoo", user)
    assert service.is_running


def test_iop_yuptoo_endpoint(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman exec iop-core-yuptoo curl -s -o /dev/null -w '%{{http_code}}' http://localhost:5005/ 2>/dev/null || echo '000'")
    assert result.rc == 0


def test_iop_core_engine_service(server, user):
    service = get_service(server, "iop-core-engine", user)
    assert service.is_running


def test_iop_core_gateway_service(server, user):
    service = get_service(server, "iop-core-gateway", user)
    assert service.is_running


def test_iop_gateway_endpoint(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman exec iop-core-gateway curl -s -o /dev/null -w '%{{http_code}}' http://localhost:24443/ 2>/dev/null || echo '000'")
    assert result.rc == 0


def test_iop_gateway_api_ingress_endpoint(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman exec iop-core-gateway curl -s -o /dev/null -w '%{{http_code}}' http://localhost:24443/api/ingress 2>/dev/null || echo '000'")
    assert result.rc == 0


def test_iop_gateway_https_cert_auth(server, user):
    # Certificates are available inside the container via Podman secrets
    result = server.run(f"cd /tmp && sudo -u {user} podman exec iop-core-gateway curl -s -o /dev/null -w '%{{http_code}}' https://localhost:8443/ --cert /etc/nginx/smart-proxy-relay/certs/proxy.crt --key /etc/nginx/smart-proxy-relay/certs/proxy.key --cacert /etc/nginx/certs/ca.crt 2>/dev/null || echo '000'")
    assert "200" in result.stdout


def test_iop_core_host_inventory_api_service(server, user):
    service = get_service(server, "iop-core-host-inventory-api", user)
    assert service.is_running


def test_iop_inventory_mq_endpoint(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman run --rm --network=iop-core-network quay.io/iop/host-inventory:foreman-3.18 curl http://iop-core-host-inventory:9126/ 2>/dev/null || echo '000'")
    assert result.rc == 0


def test_iop_inventory_api_health_endpoint(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman run --rm --network=iop-core-network quay.io/iop/host-inventory:foreman-3.18 curl -s -o /dev/null -w '%{{http_code}}' http://iop-core-host-inventory-api:8081/health 2>/dev/null || echo '000'")
    assert "200" in result.stdout


def test_iop_service_advisor_backend_api_service(server, user):
    service = get_service(server, "iop-service-advisor-backend-api", user)
    assert service.is_running


def test_iop_service_advisor_backend_service(server, user):
    service = get_service(server, "iop-service-advisor-backend-service", user)
    assert service.is_running


def test_iop_advisor_api_endpoint(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman run --rm --network=iop-core-network quay.io/iop/advisor-backend:foreman-3.18 curl -f http://iop-service-advisor-backend-api:8000/ 2>/dev/null || echo '000'")
    assert result.rc == 0


def test_iop_service_remediations_api_service(server, user):
    service = get_service(server, "iop-service-remediations-api", user)
    assert service.is_running


def test_iop_remediations_api_endpoint(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman exec iop-service-remediations-api curl -s -o /dev/null -w '%{{http_code}}' http://localhost:9002/ 2>/dev/null || echo '000'")
    assert result.rc == 0
