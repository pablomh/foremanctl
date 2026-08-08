import pytest

from tests.conftest import _record_diagnostic

ROLE_NAME = "theforeman.foremanctltest"


def test_foreman_ansible_plugin_installed(foreman_plugins):
    assert 'foreman_ansible' in foreman_plugins


@pytest.fixture(scope="module")
def ansible_proxy_id(foremanapi):
    proxies = foremanapi.list('smart_proxies')
    for proxy in proxies:
        if any(f['name'] == 'Ansible' for f in proxy.get('features', [])):
            return proxy['id']
    pytest.skip("No smart proxy with Ansible feature found")


@pytest.fixture(scope="module")
def ansible_role(server, foremanapi, ansible_proxy_id):
    setup = server.run(f"mkdir -p /var/lib/foreman-proxy/ansible/roles/{ROLE_NAME}/tasks")
    assert setup.succeeded

    write = server.run(f"echo '- command: uptime' > /var/lib/foreman-proxy/ansible/roles/{ROLE_NAME}/tasks/main.yml")
    assert write.succeeded

    assert foremanapi.resource_action('ansible_roles', 'fetch', params={'proxy_id': ansible_proxy_id})

    assert foremanapi.resource_action('ansible_roles', 'sync', params={'proxy_id': ansible_proxy_id, 'role_names': [ROLE_NAME]})

    for task in foremanapi.list('foreman_tasks', search='label ~ SyncRolesAndVariables and state != stopped'):
        foremanapi.wait_for_task(task)

    yield ROLE_NAME


def test_import_ansible_role(ansible_role, foremanapi):
    assert foremanapi.list('ansible_roles', search=f'name={ansible_role}')


@pytest.fixture
def registered_client(
    client_environment,
    activation_key,
    organization,
    foremanapi,
    client,
    client_fqdn,
    remote_execution_authorized_proxy_key,
    capsys,
):
    client.run('dnf install -y subscription-manager')
    rcmd = foremanapi.create('registration_commands', {'organization_id': organization['id'], 'insecure': True, 'activation_keys': [activation_key['name']], 'force': True})
    client.run_test(rcmd['registration_command'])

    # --- BEGIN TEMPORARY DIAGNOSTIC INSTRUMENTATION (SSH key identity mismatch investigation) ---
    # NOTE ON ORDERING: `remote_execution_authorized_proxy_key` (a fixture dependency above)
    # already injected the foreman-proxy container's key into the client's authorized_keys
    # BEFORE the registration command above ran. So this snapshot reflects
    # [manually-injected proxy key] + [whatever the registration script itself added, if
    # anything]. Diff it against the CLIENT_AUTHORIZED_KEYS_BEFORE_FIXTURE line that fixture
    # already logged (in tests/conftest.py) to see what the registration script contributed
    # on its own. This is purely additive logging; it does not change pass/fail behavior.
    # Safe to delete this block once the investigation concludes.
    authorized_keys_after_registration = client.run(
        "cat /root/.ssh/authorized_keys 2>/dev/null || echo '<authorized_keys missing or empty>'"
    ).stdout
    _record_diagnostic(capsys, "CLIENT_AUTHORIZED_KEYS_AFTER_REGISTRATION", authorized_keys_after_registration)

    try:
        host_info = foremanapi.show('hosts', {'id': client_fqdn})
        host_summary = (
            f"id={host_info.get('id')} name={host_info.get('name')!r} "
            f"organization={host_info.get('organization_name')!r} "
            f"location={host_info.get('location_name')!r} "
            f"subnet_id={host_info.get('subnet_id')} subnet_name={host_info.get('subnet_name')!r} "
            f"subnet6_id={host_info.get('subnet6_id')} subnet6_name={host_info.get('subnet6_name')!r}"
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics must never break the fixture
        host_summary = f"<failed to fetch host info for {client_fqdn}: {exc!r}>"
    _record_diagnostic(capsys, "REGISTERED_HOST_SUBNET_ORG_INFO", host_summary)

    try:
        rex_settings = foremanapi.list('settings', params={'search': 'name ~ remote_execution'})
        rex_settings_summary = "\n".join(
            f"{setting.get('name')}={setting.get('value')!r} (default={setting.get('default')!r})"
            for setting in rex_settings
        ) or '<no remote_execution settings returned>'
    except Exception as exc:  # noqa: BLE001 - diagnostics must never break the fixture
        rex_settings_summary = f"<failed to fetch remote_execution settings: {exc!r}>"
    _record_diagnostic(capsys, "REMOTE_EXECUTION_PROXY_SELECTION_SETTINGS", rex_settings_summary)
    # --- END TEMPORARY DIAGNOSTIC INSTRUMENTATION ---

    yield client_fqdn
    try:
        foremanapi.delete('hosts', {'id': client_fqdn})
    except Exception:
        pass


def test_run_ansible_role(ansible_role, ansible_proxy_id, organization, registered_client, foremanapi, server):
    org_id = organization['id']

    roles = foremanapi.list('ansible_roles', search=f'name={ansible_role}')
    assert foremanapi.resource_action('hosts', 'assign_ansible_roles', params={'organization_id': org_id, 'id': registered_client, 'ansible_role_ids': [roles[0]['id']]})

    assert foremanapi.update('smart_proxies', {'id': ansible_proxy_id, 'organization_ids': [org_id]})

    assert foremanapi.resource_action('hosts', 'play_roles', params={'organization_id': org_id, 'id': registered_client})

    tasks = foremanapi.list('foreman_tasks', search='label = Actions::RemoteExecution::RunHostsJob')
    for task in tasks:
        foremanapi.wait_for_task(task)

    assert foremanapi.list('config_reports', search=f'host={registered_client} origin=Ansible')


def test_run_command_via_ansible(registered_client, foremanapi):
    templates = foremanapi.list('job_templates', search='name = "Run Command - Ansible Default"')
    job = foremanapi.create('job_invocations', {
        'job_template_id': templates[0]['id'],
        'inputs': {'command': 'uptime'},
        'search_query': f'name = {registered_client}',
        'targeting_type': 'static_query',
    })
    task = foremanapi.wait_for_task(job['task'])
    assert task['result'] == 'success'
