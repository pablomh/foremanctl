import os

import yaml

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.abspath(os.path.join(TEST_DIR, "..", "..", "src"))
ROLE_TASKS = os.path.join(SRC_DIR, "roles", "post_install", "tasks", "main.yaml")
REGISTRATION_DEFAULTS_TASKS = os.path.join(
    SRC_DIR, "roles", "post_install", "tasks", "registration_defaults.yaml"
)


def _load_yaml(path):
    with open(path, "r") as handle:
        return yaml.safe_load(handle)


def _load_task(path, task_name):
    tasks = _load_yaml(path)
    return next(task for task in tasks if task.get("name") == task_name)


def test_post_install_includes_remote_execution_registration_defaults():
    task = _load_task(ROLE_TASKS, "Configure registration defaults")

    assert task["ansible.builtin.include_tasks"] == "registration_defaults.yaml"
    when_condition = task["when"] if isinstance(task["when"], list) else [task["when"]]
    assert "enabled_features | has_feature('remote-execution')" in when_condition


def test_registration_defaults_enable_remote_execution_bootstrap():
    lookup_task = _load_task(
        REGISTRATION_DEFAULTS_TASKS,
        "Look up remote execution registration setting",
    )
    assert lookup_task["theforeman.foreman.setting_info"]["name"] == "host_registration_remote_execution"

    enable_task = _load_task(
        REGISTRATION_DEFAULTS_TASKS,
        "Enable remote execution bootstrap in registration commands",
    )
    setting = enable_task["theforeman.foreman.setting"]

    assert setting["name"] == "host_registration_remote_execution"
    assert setting["value"] is True

    when_condition = enable_task["when"] if isinstance(enable_task["when"], list) else [enable_task["when"]]
    assert "_post_install_remote_execution_registration_setting.setting is defined" in when_condition
    assert "_post_install_remote_execution_registration_setting.setting is not none" in when_condition
