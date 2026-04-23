import pytest

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

def test_foreman_rex(client_environment, activation_key, organization, foremanapi, client, client_fqdn, rex_mode):
    if rex_mode != 'ssh':
        pytest.skip("SSH REX mode not active")
    client.run('dnf install -y subscription-manager')
    rcmd = foremanapi.create('registration_commands', {'organization_id': organization['id'], 'insecure': True, 'activation_keys': [activation_key['name']], 'force': True})
    client.run_test(rcmd['registration_command'])
    job = foremanapi.create('job_invocations', {'feature': 'run_script', 'inputs': {'command': 'uptime'}, 'search_query': f'name = {client_fqdn}', 'targeting_type': 'static_query'})
    task = foremanapi.wait_for_task(job['task'])
    assert task['result'] == 'success'
    foremanapi.delete('hosts', {'id': client_fqdn})

def test_foreman_rex_pull_mqtt(client_environment, activation_key, organization, foremanapi, client, client_fqdn, server, rex_mode):
    if rex_mode != 'pull-mqtt':
        pytest.skip("pull-mqtt REX mode not active")
    client.run('dnf install -y subscription-manager')
    rcmd = foremanapi.create('registration_commands', {
        'organization_id': organization['id'],
        'insecure': True,
        'activation_keys': [activation_key['name']],
        'force': True,
        'setup_remote_execution_pull': True,
    })
    client.run_test(rcmd['registration_command'])

    ygg_status = client.run('systemctl status yggdrasild')
    print(f"DEBUG MQTT: yggdrasild status rc={ygg_status.rc}")
    print(f"DEBUG MQTT: yggdrasild status: {ygg_status.stdout[-500:]}")
    ygg_conf = client.run('cat /etc/yggdrasil/config.toml 2>/dev/null || echo "no config"')
    print(f"DEBUG MQTT: yggdrasil config: {ygg_conf.stdout[:500]}")
    mqtt_check = client.run(f'bash -c "echo > /dev/tcp/quadlet.example.com/1883" 2>&1')
    print(f"DEBUG MQTT: client->mosquitto connectivity rc={mqtt_check.rc}")
    mosquitto_logs = server.run('podman logs --tail 30 mosquitto 2>&1')
    print(f"DEBUG MQTT: mosquitto logs: {mosquitto_logs.stdout[-1000:]}")
    proxy_logs = server.run('podman logs --tail 30 foreman-proxy 2>&1')
    print(f"DEBUG MQTT: proxy logs: {proxy_logs.stdout[-1000:]}")

    job = foremanapi.create('job_invocations', {'feature': 'run_script', 'inputs': {'command': 'uptime'}, 'search_query': f'name = {client_fqdn}', 'targeting_type': 'static_query'})
    try:
        task = foremanapi.wait_for_task(job['task'])
    except Exception as e:
        print(f"DEBUG MQTT: task exception: {e}")
        job_detail = foremanapi.resource_action('job_invocations', 'show', {'id': job['id']}, ignore_task_errors=True)
        if job_detail:
            print(f"DEBUG MQTT: job status={job_detail.get('status_label')} succeeded={job_detail.get('succeeded')} failed={job_detail.get('failed')}")
        mosquitto_logs2 = server.run('podman logs --tail 50 mosquitto 2>&1')
        print(f"DEBUG MQTT: mosquitto logs (post-job): {mosquitto_logs2.stdout[-1500:]}")
        proxy_logs2 = server.run('podman logs --tail 50 foreman-proxy 2>&1')
        print(f"DEBUG MQTT: proxy logs (post-job): {proxy_logs2.stdout[-1500:]}")
        ygg_logs = client.run('journalctl -u yggdrasild --no-pager -n 30')
        print(f"DEBUG MQTT: yggdrasild journal: {ygg_logs.stdout[-1500:]}")
        raise
    assert task['result'] == 'success'
    foremanapi.delete('hosts', {'id': client_fqdn})
