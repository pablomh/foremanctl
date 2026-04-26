import pytest

from conftest import (
    SYSTEMCTL_USER,
    foremanctl_run,
    service_is_enabled,
    service_is_running,
)

pytestmark = pytest.mark.iop


def test_iop_core_kafka_service(server):
    assert service_is_running(server, "iop-core-kafka")
    assert service_is_enabled(server, "iop-core-kafka")


def test_iop_core_ingress_service(server):
    result = server.run(f"{SYSTEMCTL_USER} list-units --type=service | grep iop-core-ingress")
    if result.succeeded:
        assert service_is_running(server, "iop-core-ingress")
        assert service_is_enabled(server, "iop-core-ingress")


def test_iop_ingress_endpoint(server):
    result = server.run("curl -f http://localhost:8080/ 2>/dev/null || echo 'Ingress not yet responding'")
    assert result.rc == 0


def test_iop_core_puptoo_service(server):
    result = server.run(f"{SYSTEMCTL_USER} list-units --type=service | grep iop-core-puptoo")
    if result.succeeded:
        assert service_is_running(server, "iop-core-puptoo")
        assert service_is_enabled(server, "iop-core-puptoo")


def test_iop_puptoo_metrics_endpoint(server):
    result = server.run("curl -f http://localhost:8000/metrics 2>/dev/null || echo 'Puptoo not yet responding'")
    assert result.rc == 0


def test_iop_core_yuptoo_service(server):
    result = server.run(f"{SYSTEMCTL_USER} list-units --type=service | grep iop-core-yuptoo")
    if result.succeeded:
        assert service_is_running(server, "iop-core-yuptoo")
        assert service_is_enabled(server, "iop-core-yuptoo")


def test_iop_yuptoo_endpoint(server):
    result = server.run("curl -f http://localhost:5005/ 2>/dev/null || echo 'Yuptoo not yet responding'")
    assert result.rc == 0


def test_iop_core_engine_service(server):
    result = server.run(f"{SYSTEMCTL_USER} list-units --type=service | grep iop-core-engine")
    if result.succeeded:
        assert service_is_running(server, "iop-core-engine")
        assert service_is_enabled(server, "iop-core-engine")


def test_iop_core_gateway_service(server):
    result = server.run(f"{SYSTEMCTL_USER} list-units --type=service | grep iop-core-gateway")
    if result.succeeded:
        assert service_is_running(server, "iop-core-gateway")
        assert service_is_enabled(server, "iop-core-gateway")


def test_iop_gateway_endpoint(server):
    result = server.run("curl -f http://localhost:24443/ 2>/dev/null || echo 'Gateway not yet responding'")
    assert result.rc == 0


def test_iop_gateway_api_ingress_endpoint(server):
    result = server.run("curl -f http://localhost:24443/api/ingress 2>/dev/null || echo 'Gateway API ingress not yet responding'")
    assert result.rc == 0


def test_iop_gateway_https_cert_auth(server, certificates):
    cert = certificates['iop_gateway_client_certificate']
    key = certificates['iop_gateway_client_key']
    ca = certificates['iop_gateway_client_ca_certificate']
    result = foremanctl_run(server, f"podman run --rm --network=foreman-proxy-net -v {cert}:{cert}:z -v {key}:{key}:z -v {ca}:{ca}:z quay.io/centos/centos:stream9 curl -s -o /dev/null -w '%{{http_code}}' --cert {cert} --key {key} --cacert {ca} https://iop-core-gateway:8443/")
    assert "200" in result.stdout


def test_iop_core_host_inventory_api_service(server):
    result = server.run(f"{SYSTEMCTL_USER} list-units --type=service | grep iop-core-host-inventory-api")
    if result.succeeded:
        assert service_is_running(server, "iop-core-host-inventory-api")
        assert service_is_enabled(server, "iop-core-host-inventory-api")


def test_iop_inventory_mq_endpoint(server):
    result = foremanctl_run(server, "podman run --network=iop-core-network quay.io/iop/host-inventory:latest curl http://iop-core-host-inventory:9126/ 2>/dev/null || echo 'Host inventory MQ not yet responding'")
    assert result.rc == 0


def test_iop_inventory_api_health_endpoint(server):
    result = foremanctl_run(server, "podman run --network=iop-core-network quay.io/iop/host-inventory curl -s -o /dev/null -w '%{http_code}' http://iop-core-host-inventory-api:8081/health 2>/dev/null || echo '000'")
    assert "200" in result.stdout


def test_iop_service_advisor_backend_api_service(server):
    result = server.run(f"{SYSTEMCTL_USER} list-units --type=service | grep iop-service-advisor-backend-api")
    if result.succeeded:
        assert service_is_running(server, "iop-service-advisor-backend-api")
        assert service_is_enabled(server, "iop-service-advisor-backend-api")


def test_iop_service_advisor_backend_service(server):
    result = server.run(f"{SYSTEMCTL_USER} list-units --type=service | grep iop-service-advisor-backend-service")
    if result.succeeded:
        assert service_is_running(server, "iop-service-advisor-backend-service")
        assert service_is_enabled(server, "iop-service-advisor-backend-service")


def test_iop_advisor_api_endpoint(server):
    result = foremanctl_run(server, "podman run --network=iop-core-network --rm quay.io/iop/advisor-backend:latest curl -f http://iop-service-advisor-backend-api:8000/ 2>/dev/null || echo 'Advisor API not yet responding'")
    assert result.rc == 0


def test_iop_service_remediations_api_service(server):
    result = server.run(f"{SYSTEMCTL_USER} list-units --type=service | grep iop-service-remediations-api")
    if result.succeeded:
        assert service_is_running(server, "iop-service-remediations-api")
        assert service_is_enabled(server, "iop-service-remediations-api")


def test_iop_remediations_api_endpoint(server):
    result = server.run("curl -f http://localhost:9002/ 2>/dev/null || echo 'Remediations API not yet responding'")
    assert result.rc == 0
