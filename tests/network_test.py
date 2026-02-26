import pytest


def test_netavark_installed(server):
    """Verify netavark network backend is installed"""
    pkg = server.package("netavark")
    assert pkg.is_installed


def test_aardvark_dns_installed(server):
    """Verify aardvark-dns is installed for container DNS resolution"""
    pkg = server.package("aardvark-dns")
    assert pkg.is_installed


def test_passt_installed(server):
    """Verify passt is installed for improved port forwarding"""
    pkg = server.package("passt")
    assert pkg.is_installed


def test_podman_network_backend(server, user):
    """Verify podman is configured to use netavark backend"""
    if user:
        cmd = server.run(f"cd /tmp && sudo -u {user} podman info --format '{{{{.Host.NetworkBackend}}}}'")
    else:
        cmd = server.run("podman info --format '{{.Host.NetworkBackend}}'")
    assert cmd.succeeded
    assert "netavark" in cmd.stdout.lower()


def test_podman_network_create_user(server, user):
    """Test that rootless user can create private networks"""
    if not user:
        pytest.skip("Test only applies to rootless mode")

    network_name = "test-network-verify"

    # Create network
    create_cmd = server.run(f"cd /tmp && sudo -u {user} podman network create {network_name}")
    assert create_cmd.succeeded, f"Failed to create network: {create_cmd.stderr}"

    # Verify network exists
    list_cmd = server.run(f"cd /tmp && sudo -u {user} podman network ls --format '{{{{.Name}}}}'")
    assert network_name in list_cmd.stdout

    # Cleanup: Remove network
    remove_cmd = server.run(f"cd /tmp && sudo -u {user} podman network rm {network_name}")
    assert remove_cmd.succeeded, f"Failed to remove network: {remove_cmd.stderr}"


def test_podman_network_dns_resolution(server, user):
    """Test that aardvark-dns provides container name resolution"""
    if not user:
        pytest.skip("Test only applies to rootless mode")

    network_name = "test-dns-network"
    container1 = "test-dns-container1"
    container2 = "test-dns-container2"

    try:
        # Create network
        server.run(f"cd /tmp && sudo -u {user} podman network create {network_name}")

        # Start first container
        server.run(f"cd /tmp && sudo -u {user} podman run -d --name {container1} --network {network_name} quay.io/centos/centos:stream9 sleep 300")

        # Start second container and test DNS resolution to first container using getent
        dns_cmd = server.run(f"cd /tmp && sudo -u {user} podman run --rm --network {network_name} quay.io/centos/centos:stream9 getent hosts {container1}")

        assert dns_cmd.succeeded, f"DNS resolution failed: {dns_cmd.stderr}"
        assert container1 in dns_cmd.stdout, f"Container name not resolved in output: {dns_cmd.stdout}"

    finally:
        # Cleanup
        server.run(f"cd /tmp && sudo -u {user} podman rm -f {container1} {container2} || true")
        server.run(f"cd /tmp && sudo -u {user} podman network rm {network_name} || true")
