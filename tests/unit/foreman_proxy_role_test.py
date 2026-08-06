import os

import yaml

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.abspath(os.path.join(TEST_DIR, '..', '..', 'src'))
ROLE_TASKS = os.path.join(SRC_DIR, 'roles', 'foreman_proxy', 'tasks', 'main.yaml')


def _load_task(task_name):
    with open(ROLE_TASKS, 'r') as task_file:
        tasks = yaml.safe_load(task_file)
    return next(task for task in tasks if task.get('name') == task_name)


def test_wait_for_proxy_uses_registration_url():
    task = _load_task("Wait for Foreman Proxy API to be reachable from Foreman")

    assert "{{ foreman_proxy_registration_url }}/v2/features" in task["ansible.builtin.command"]["argv"]

    when_condition = task["when"] if isinstance(task["when"], list) else [task["when"]]
    assert "enabled_features | has_feature('foreman')" in when_condition


def test_proxy_registration_keeps_public_name_and_internal_url():
    task = _load_task("Register Foreman Proxy to Foreman")
    smart_proxy = task["theforeman.foreman.smart_proxy"]

    assert smart_proxy["name"] == "{{ foreman_proxy_fqdn }}"
    assert smart_proxy["url"] == "{{ foreman_proxy_registration_url }}"
