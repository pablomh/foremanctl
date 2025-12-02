import pytest


def test_kafka_service(server, user):
    result = server.run(f"systemctl --machine={user}@ --user is-active iop-core-kafka")
    assert result.succeeded
    assert "active" in result.stdout


def test_kafka_volume(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman volume ls --format '{{{{.Name}}}}'")
    assert result.succeeded
    assert "iop-core-kafka-data" in result.stdout


def test_kafka_topics_initialized(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman exec iop-core-kafka /opt/kafka/init.sh --check")
    assert result.succeeded


def test_kafka_secrets(server, user):
    secrets = [
        'iop-core-kafka-init-start',
        'iop-core-kafka-server-properties',
        'iop-core-kafka-init'
    ]

    result = server.run(f"cd /tmp && sudo -u {user} podman secret ls --format '{{{{.Name}}}}'")
    assert result.succeeded

    for secret_name in secrets:
        assert secret_name in result.stdout


def test_kafka_config_content(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman secret inspect iop-core-kafka-server-properties --showsecret")
    assert result.succeeded

    config_data = result.stdout.strip()
    assert "advertised.listeners=PLAINTEXT://iop-core-kafka:9092" in config_data
    assert "controller.quorum.voters=1@iop-core-kafka:9093" in config_data


def test_kafka_container_running(server, user):
    result = server.run(f"cd /tmp && sudo -u {user} podman inspect iop-core-kafka --format '{{{{.State.Status}}}}'")
    assert result.succeeded
    assert "running" in result.stdout


def test_kafka_quadlet_file(server, user):
    result = server.run(f"getent passwd {user}")
    assert result.succeeded
    user_home = result.stdout.split(':')[5]
    quadlet_file = server.file(f"{user_home}/.config/containers/systemd/iop-core-kafka.container")
    assert quadlet_file.exists
    assert quadlet_file.is_file


def test_kafka_topic_creation(server, user):
    topics = [
        "platform.upload.available",
        "platform.inventory.events",
        "platform.system-profile",
        "advisor.recommendations",
        "advisor.payload-tracker",
        "advisor.rules-results",
        "remediations.updates",
        "remediations.status",
        "vulnerability.uploads",
        "vulnerability.evaluator",
        "vulnerability.manager",
        "vmaas.vulnerability.updates",
        "vmaas.package.updates",
        "puptoo.opening",
        "puptoo.validation",
        "yuptoo.opening",
        "yuptoo.validation"
    ]

    result = server.run(f"cd /tmp && sudo -u {user} podman exec iop-core-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server iop-core-kafka:9092 --list")
    assert result.succeeded

    for topic in topics:
        assert topic in result.stdout
