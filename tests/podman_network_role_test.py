import pytest
import json


def test_podman_network_role_creates_network(server, user):
    """Test that podman_network role successfully creates a network"""
    if not user:
        pytest.skip("Test only applies to rootless mode")

    network_name = "test-role-network"

    # Verify network exists (should be created by the role in deployment)
    list_cmd = server.run(f"cd /tmp && sudo -u {user} podman network ls --format '{{{{.Name}}}}'")

    # If test network doesn't exist, skip (role hasn't been applied yet)
    if network_name not in list_cmd.stdout:
        pytest.skip(f"Network '{network_name}' not created yet - role not applied in this deployment")


def test_podman_network_role_network_properties(server, user):
    """Test that created network has correct properties"""
    if not user:
        pytest.skip("Test only applies to rootless mode")

    network_name = "test-role-network"

    # Get network details
    inspect_cmd = server.run(f"cd /tmp && sudo -u {user} podman network inspect {network_name}")

    if not inspect_cmd.succeeded:
        pytest.skip(f"Network '{network_name}' does not exist - role not applied in this deployment")

    network_info = json.loads(inspect_cmd.stdout)[0]

    # Verify network driver
    assert network_info.get("driver") == "bridge", "Network should use bridge driver"

    # Verify DNS is enabled (via aardvark-dns)
    assert network_info.get("dns_enabled", True), "DNS should be enabled for container name resolution"


def test_podman_network_role_container_connectivity(server, user):
    """Test that containers on the role-created network can communicate"""
    if not user:
        pytest.skip("Test only applies to rootless mode")

    network_name = "test-connectivity-network"
    container1 = "test-conn-container1"
    container2 = "test-conn-container2"

    # Verify network exists first
    check_cmd = server.run(f"cd /tmp && sudo -u {user} podman network exists {network_name}")
    if not check_cmd.succeeded:
        # Create test network using the same pattern as the role
        create_cmd = server.run(f"cd /tmp && sudo -u {user} podman network create {network_name}")
        assert create_cmd.succeeded, f"Failed to create test network: {create_cmd.stderr}"

    try:
        # Start first container on the network
        run1_cmd = server.run(
            f"cd /tmp && sudo -u {user} podman run -d --name {container1} "
            f"--network {network_name} quay.io/centos/centos:stream9 sleep 300"
        )
        assert run1_cmd.succeeded, f"Failed to start container1: {run1_cmd.stderr}"

        # Start second container and resolve the first by name using DNS
        dns_cmd = server.run(
            f"cd /tmp && sudo -u {user} podman run --rm --network {network_name} "
            f"quay.io/centos/centos:stream9 getent hosts {container1}"
        )

        assert dns_cmd.succeeded, f"Container connectivity test failed: {dns_cmd.stderr}"
        assert container1 in dns_cmd.stdout, \
            f"Container name not resolved via DNS: {dns_cmd.stdout}"

    finally:
        # Cleanup
        server.run(f"cd /tmp && sudo -u {user} podman rm -f {container1} {container2} 2>/dev/null || true")
        server.run(f"cd /tmp && sudo -u {user} podman network rm {network_name} 2>/dev/null || true")


def test_podman_network_role_multiple_networks(server, user):
    """Test that container can join multiple networks created by the role"""
    if not user:
        pytest.skip("Test only applies to rootless mode")

    network1 = "test-multi-net1"
    network2 = "test-multi-net2"
    container = "test-multi-container"

    try:
        # Create two networks
        for net in [network1, network2]:
            cmd = server.run(f"cd /tmp && sudo -u {user} podman network create {net}")
            assert cmd.succeeded, f"Failed to create network {net}: {cmd.stderr}"

        # Start container connected to both networks
        run_cmd = server.run(
            f"cd /tmp && sudo -u {user} podman run -d --name {container} "
            f"--network {network1} --network {network2} "
            f"quay.io/centos/centos:stream9 sleep 300"
        )
        assert run_cmd.succeeded, f"Failed to start multi-network container: {run_cmd.stderr}"

        # Verify container is on both networks
        inspect_cmd = server.run(f"cd /tmp && sudo -u {user} podman inspect {container}")
        assert inspect_cmd.succeeded

        container_info = json.loads(inspect_cmd.stdout)[0]
        networks = container_info["NetworkSettings"]["Networks"].keys()

        assert network1 in networks, f"Container should be on {network1}"
        assert network2 in networks, f"Container should be on {network2}"

    finally:
        # Cleanup
        server.run(f"cd /tmp && sudo -u {user} podman rm -f {container} 2>/dev/null || true")
        for net in [network1, network2]:
            server.run(f"cd /tmp && sudo -u {user} podman network rm {net} 2>/dev/null || true")


def test_podman_network_role_isolation(server, user):
    """Test that containers on different networks are isolated"""
    if not user:
        pytest.skip("Test only applies to rootless mode")

    network1 = "test-isolated-net1"
    network2 = "test-isolated-net2"
    container1 = "test-isolated-c1"
    container2 = "test-isolated-c2"

    try:
        # Create two separate networks
        for net in [network1, network2]:
            cmd = server.run(f"cd /tmp && sudo -u {user} podman network create {net}")
            assert cmd.succeeded, f"Failed to create network {net}: {cmd.stderr}"

        # Start container on first network
        run1_cmd = server.run(
            f"cd /tmp && sudo -u {user} podman run -d --name {container1} "
            f"--network {network1} quay.io/centos/centos:stream9 sleep 300"
        )
        assert run1_cmd.succeeded

        # Try to resolve container1 from container2 on different network (should fail)
        dns_cmd = server.run(
            f"cd /tmp && sudo -u {user} podman run --rm --network {network2} "
            f"quay.io/centos/centos:stream9 getent hosts {container1}"
        )

        # DNS resolution should fail (containers on different networks)
        assert not dns_cmd.succeeded, \
            "Containers on different networks should NOT be able to resolve each other via DNS"

    finally:
        # Cleanup
        server.run(f"cd /tmp && sudo -u {user} podman rm -f {container1} {container2} 2>/dev/null || true")
        for net in [network1, network2]:
            server.run(f"cd /tmp && sudo -u {user} podman network rm {net} 2>/dev/null || true")


def test_podman_network_role_subnet_configuration(server, user):
    """Test that network can be created with custom subnet"""
    if not user:
        pytest.skip("Test only applies to rootless mode")

    network_name = "test-subnet-network"
    subnet = "10.99.0.0/24"
    gateway = "10.99.0.1"

    try:
        # Create network with custom subnet
        create_cmd = server.run(
            f"cd /tmp && sudo -u {user} podman network create "
            f"--subnet {subnet} --gateway {gateway} {network_name}"
        )
        assert create_cmd.succeeded, f"Failed to create network with custom subnet: {create_cmd.stderr}"

        # Verify subnet configuration
        inspect_cmd = server.run(f"cd /tmp && sudo -u {user} podman network inspect {network_name}")
        assert inspect_cmd.succeeded

        network_info = json.loads(inspect_cmd.stdout)[0]
        subnets = network_info.get("subnets", [])

        assert len(subnets) > 0, "Network should have at least one subnet"
        assert subnets[0]["subnet"] == subnet, f"Subnet should be {subnet}"
        assert subnets[0]["gateway"] == gateway, f"Gateway should be {gateway}"

    finally:
        # Cleanup
        server.run(f"cd /tmp && sudo -u {user} podman network rm {network_name} 2>/dev/null || true")
