import os

import yaml

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.abspath(os.path.join(TEST_DIR, '..', '..', 'src'))
ROLE_TASKS = os.path.join(SRC_DIR, 'roles', 'foreman_proxy', 'tasks', 'main.yaml')
ROLE_DEFAULTS = os.path.join(SRC_DIR, 'roles', 'foreman_proxy', 'defaults', 'main.yaml')
ROLE_HANDLERS = os.path.join(SRC_DIR, 'roles', 'foreman_proxy', 'handlers', 'main.yml')


def _load_tasks():
    with open(ROLE_TASKS, 'r') as task_file:
        return yaml.safe_load(task_file)


def _load_task(task_name):
    return next(task for task in _load_tasks() if task.get('name') == task_name)


def _load_handlers():
    with open(ROLE_HANDLERS, 'r') as handlers_file:
        return yaml.safe_load(handlers_file)


def _load_defaults():
    with open(ROLE_DEFAULTS, 'r') as defaults_file:
        return yaml.safe_load(defaults_file)


def test_proxy_defaults_use_public_registration_url():
    defaults = _load_defaults()

    assert defaults["foreman_proxy_name"] == "{{ ansible_facts['fqdn'] }}"
    assert defaults["foreman_proxy_url"] == "https://{{ foreman_proxy_name }}:{{ foreman_proxy_https_port }}"
    assert defaults["foreman_proxy_registration_url"] == "{{ foreman_proxy_url }}"


def test_wait_for_proxy_uses_registration_url():
    task = _load_task("Wait for Foreman Proxy API to be reachable from Foreman")

    assert "{{ foreman_proxy_registration_url }}/v2/features" in task["ansible.builtin.command"]["argv"]

    when_condition = task["when"] if isinstance(task["when"], list) else [task["when"]]
    assert "enabled_features | has_feature('foreman')" in when_condition


def test_proxy_registration_keeps_public_name_and_registration_url():
    task = _load_task("Register Foreman Proxy to Foreman")
    smart_proxy = task["theforeman.foreman.smart_proxy"]

    assert smart_proxy["name"] == "{{ foreman_proxy_name }}"
    assert smart_proxy["url"] == "{{ foreman_proxy_registration_url }}"


def test_refresh_foreman_proxy_is_an_unconditional_handler():
    # Regression test: "Refresh Foreman Proxy" must be a plain, unconditional
    # handler (matching master), not gated behind a guard. A previous guard fed by
    # a "Check whether Foreman Proxy is registered" handler that nothing ever
    # notified always evaluated false, silently skipping the refresh and leaving
    # the proxy's pubkey/ca_pubkey uncached forever.
    handlers = _load_handlers()
    handler_names = [handler.get('name') for handler in handlers]

    assert 'Restart Foreman Proxy' in handler_names
    assert 'Refresh Foreman Proxy' in handler_names
    assert 'Check whether Foreman Proxy is registered' not in handler_names

    refresh_handler = next(h for h in handlers if h.get('name') == 'Refresh Foreman Proxy')
    assert 'when' not in refresh_handler
    assert refresh_handler['theforeman.foreman.smart_proxy_refresh']['smart_proxy'] == "{{ foreman_proxy_name }}"


def test_feature_task_files_notify_restart_and_refresh_together():
    # Matching master: every task that can change the proxy's on-disk config
    # notifies both handlers together, so a refresh always follows a restart.
    role_dir = os.path.join(SRC_DIR, 'roles', 'foreman_proxy', 'tasks')
    notifying_files = (
        'feature.yaml',
        os.path.join('feature', 'ansible.yaml'),
        os.path.join('feature', 'remote_execution_ssh.yaml'),
    )
    found_notify = False
    for relative_path in notifying_files:
        path = os.path.join(role_dir, relative_path)
        with open(path, 'r') as handle:
            content = yaml.safe_load(handle) or []
        for task in content:
            notify = task.get('notify')
            if notify is None:
                continue
            notify_list = notify if isinstance(notify, list) else [notify]
            assert notify_list == ['Restart Foreman Proxy', 'Refresh Foreman Proxy'], (
                f"{path} task {task.get('name')!r} notify list {notify_list!r} does not "
                "match master's paired Restart+Refresh notification"
            )
            found_notify = True

    assert found_notify, "expected at least one notifying task across the feature task files"


def test_refresh_cannot_fire_before_registration():
    # The only place "Refresh Foreman Proxy" can run is via a handler flush, and
    # the only flush in this role sits right after "Register Foreman Proxy to
    # Foreman" (matching master's relative ordering), so the proxy is guaranteed
    # to already exist in Foreman by the time it runs.
    tasks = _load_tasks()
    names = [task.get('name') for task in tasks]

    assert 'Register Foreman Proxy to Foreman' in names
    assert 'Refresh Foreman Proxy' not in names, (
        "Refresh Foreman Proxy should be a handler, not a plain task"
    )

    flush_indexes = [i for i, task in enumerate(tasks) if 'ansible.builtin.meta' in task]
    assert len(flush_indexes) == 1, "expected exactly one handler flush in the role"

    register_index = names.index('Register Foreman Proxy to Foreman')
    assert flush_indexes[0] == register_index + 1


def test_early_restart_before_readiness_check_is_a_plain_task_not_a_handler_flush():
    # This branch restarts the proxy container before the Foreman-reachability
    # readiness check (needed for bridge networking, unlike master's host
    # networking) via a plain imperative task rather than a notify/flush, so
    # that doing so can never also flush (and thus prematurely fire) the paired
    # "Refresh Foreman Proxy" handler notified from the same feature tasks.
    tasks = _load_tasks()
    names = [task.get('name') for task in tasks]

    assert 'Wait for Foreman Proxy API to be reachable from Foreman' in names
    readiness_index = names.index('Wait for Foreman Proxy API to be reachable from Foreman')

    early_restart = tasks[readiness_index - 1]
    assert early_restart.get('name') == 'Restart Foreman Proxy ahead of registration'
    assert 'notify' not in early_restart
    assert early_restart['ansible.builtin.systemd']['name'] == 'foreman-proxy'

    # No handler flush must occur before registration.
    register_index = names.index('Register Foreman Proxy to Foreman')
    for task in tasks[:register_index]:
        assert 'ansible.builtin.meta' not in task, (
            f"{task.get('name')!r} flushes handlers before registration"
        )
