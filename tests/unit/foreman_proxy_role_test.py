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


def test_refresh_runs_as_unconditional_task_right_after_registration():
    # Regression test: the refresh must be a plain task placed immediately after
    # registration, not a notified handler. A handler-based refresh depends on a
    # guard/notify chain to know the proxy is registered, which previously broke
    # silently (the guard's precondition handler was never notified, so it always
    # evaluated false and the proxy's pubkey was never cached).
    tasks = _load_tasks()
    names = [task.get('name') for task in tasks]

    assert 'Register Foreman Proxy to Foreman' in names
    assert 'Refresh Foreman Proxy' in names
    register_index = names.index('Register Foreman Proxy to Foreman')
    refresh_index = names.index('Refresh Foreman Proxy')
    assert refresh_index == register_index + 1

    refresh_task = tasks[refresh_index]
    assert 'when' not in refresh_task
    assert refresh_task['theforeman.foreman.smart_proxy_refresh']['smart_proxy'] == "{{ foreman_proxy_name }}"


def test_refresh_foreman_proxy_is_no_longer_a_handler():
    # The old handler-based refresh relied on a "Check whether Foreman Proxy is
    # registered" handler that nothing ever notified, so its guard was always false.
    handlers = _load_handlers()
    handler_names = [handler.get('name') for handler in handlers]

    assert 'Refresh Foreman Proxy' not in handler_names
    assert 'Check whether Foreman Proxy is registered' not in handler_names


def test_no_stray_notify_of_removed_refresh_handler():
    # A "notify: Refresh Foreman Proxy" pointing at a handler that no longer exists
    # would make Ansible fail the whole play with "handler not found".
    role_dir = os.path.join(SRC_DIR, 'roles', 'foreman_proxy', 'tasks')
    for dirpath, _dirnames, filenames in os.walk(role_dir):
        for filename in filenames:
            if not filename.endswith(('.yaml', '.yml')):
                continue
            path = os.path.join(dirpath, filename)
            with open(path, 'r') as handle:
                content = yaml.safe_load(handle) or []
            for task in content:
                notify = task.get('notify')
                if notify is None:
                    continue
                notify_list = notify if isinstance(notify, list) else [notify]
                assert 'Refresh Foreman Proxy' not in notify_list, (
                    f"{path} still notifies the removed 'Refresh Foreman Proxy' handler"
                )
