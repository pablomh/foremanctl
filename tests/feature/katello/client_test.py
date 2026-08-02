import pytest


@pytest.fixture
def remote_execution_authorized_proxy_key(server, client):
    proxy_public_key = server.check_output(
        "podman exec foreman-proxy cat /usr/share/foreman-proxy/.ssh/id_rsa_foreman_proxy.pub"
    ).strip()

    client.run_test(
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        "ssh_dir = Path('/root/.ssh')\n"
        "ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)\n"
        "authorized_keys = ssh_dir / 'authorized_keys'\n"
        "authorized_keys.touch()\n"
        "authorized_keys.chmod(0o600)\n"
        f"proxy_public_key = {proxy_public_key!r}\n"
        "lines = authorized_keys.read_text().splitlines()\n"
        "if proxy_public_key not in lines:\n"
        "    with authorized_keys.open('a', encoding='utf-8') as fh:\n"
        "        fh.write(proxy_public_key + '\\n')\n"
        "PY"
    )

    yield

    client.run(
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        "authorized_keys = Path('/root/.ssh/authorized_keys')\n"
        f"proxy_public_key = {proxy_public_key!r}\n"
        "if authorized_keys.exists():\n"
        "    filtered = [line for line in authorized_keys.read_text().splitlines() if line != proxy_public_key]\n"
        "    if filtered:\n"
        "        authorized_keys.write_text('\\n'.join(filtered) + '\\n', encoding='utf-8')\n"
        "    else:\n"
        "        authorized_keys.unlink()\n"
        "PY"
    )


def test_foreman_content_view(client_environment, activation_key, organization, foremanapi, client):
    client.run('dnf install -y subscription-manager')
    rcmd = foremanapi.create('registration_commands', {'organization_id': organization['id'], 'insecure': True, 'activation_keys': [activation_key['name']], 'force': True})
    client.run_test(rcmd['registration_command'])
    client.run('subscription-manager repos --enable=*')
    client.run_test('dnf install -y bear')
    assert client.package('bear').is_installed
    client.run('dnf remove -y bear')
    client.run('subscription-manager unregister')
    client.run('subscription-manager clean')


def test_foreman_rex(
    client_environment,
    activation_key,
    organization,
    foremanapi,
    client,
    client_fqdn,
    remote_execution_authorized_proxy_key,
):
    client.run('dnf install -y subscription-manager')
    rcmd = foremanapi.create('registration_commands', {'organization_id': organization['id'], 'insecure': True, 'activation_keys': [activation_key['name']], 'force': True})
    client.run_test(rcmd['registration_command'])
    job = foremanapi.create('job_invocations', {'feature': 'run_script', 'inputs': {'command': 'uptime'}, 'search_query': f'name = {client_fqdn}', 'targeting_type': 'static_query'})
    task = foremanapi.wait_for_task(job['task'])
    assert task['result'] == 'success'
    foremanapi.delete('hosts', {'id': client_fqdn})
