import json

from conftest import run_as


def test_iop_core_network_properties(server, user):
    """Verify iop-core-network has the expected isolation properties."""
    result = run_as(server, user, "podman network inspect iop-core-network")
    assert result.succeeded, "iop-core-network should exist"

    info = json.loads(result.stdout)[0]
    assert info.get("internal") is True, "iop-core-network should be internal (no external access)"
    options = info.get("options", {})
    assert options.get("isolate") == "true", "iop-core-network should have isolate=true"


def test_iop_core_network_isolate_blocks_cross_network_traffic(server, user):
    """Verify that containers on iop-core-network cannot reach containers on other networks.

    The isolate=true option adds nftables rules that prevent cross-network communication
    even when the destination IP would otherwise be routable through the host.
    """
    other_net = "test-iop-isolate-net"
    other_container = "test-iop-isolate-target"

    try:
        # Create a plain bridge network (no isolate) and start a target container
        create_cmd = run_as(server, user, f"podman network create {other_net}")
        assert create_cmd.succeeded, f"Failed to create test network: {create_cmd.stderr}"

        run_cmd = run_as(server, user,
            f"podman run -d --name {other_container} "
            f"--network {other_net} quay.io/centos/centos:stream9 sleep 60"
        )
        assert run_cmd.succeeded, f"Failed to start target container: {run_cmd.stderr}"

        # Get the IP address of the target container
        inspect_cmd = run_as(server, user, f"podman inspect {other_container}")
        assert inspect_cmd.succeeded
        info = json.loads(inspect_cmd.stdout)[0]
        other_ip = info["NetworkSettings"]["Networks"][other_net]["IPAddress"]
        assert other_ip, "Could not determine target container IP"

        # Try to ping the target container from inside iop-core-network.
        # With isolate=true, the ping should fail because cross-network traffic is blocked.
        ping_cmd = run_as(server, user,
            f"podman run --rm --network iop-core-network "
            f"quay.io/centos/centos:stream9 ping -c 1 -W 2 {other_ip}"
        )
        assert not ping_cmd.succeeded, (
            f"Container on iop-core-network reached {other_ip} on {other_net} — "
            f"isolate=true should block cross-network traffic"
        )

    finally:
        run_as(server, user, f"podman rm -f {other_container} 2>/dev/null || true")
        run_as(server, user, f"podman network rm {other_net} 2>/dev/null || true")
