import os

import yaml

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.abspath(os.path.join(TEST_DIR, "..", "..", "src"))
ROLE_TASKS = os.path.join(SRC_DIR, "roles", "post_install", "tasks", "main.yaml")
REGISTRATION_DEFAULTS_TASKS = os.path.join(
    SRC_DIR, "roles", "post_install", "tasks", "registration_defaults.yaml"
)
REMOTE_EXECUTION_REGISTRATION_SETTING = "host_registration_remote_execution"
REMOTE_EXECUTION_SETTING_REGISTER = "_post_install_remote_execution_registration_setting"


def _load_yaml(path):
    with open(path, "r") as handle:
        return yaml.safe_load(handle)


def _load_task(path, task_name):
    tasks = _load_yaml(path)
    return next(task for task in tasks if task.get("name") == task_name)


def _as_list(value):
    return value if isinstance(value, list) else [value]


def test_post_install_includes_remote_execution_registration_defaults():
    task = _load_task(ROLE_TASKS, "Configure registration defaults")

    assert task["ansible.builtin.include_tasks"] == "registration_defaults.yaml"
    when_condition = _as_list(task["when"])
    assert "enabled_features | has_feature('remote-execution')" in when_condition


def test_registration_defaults_enable_remote_execution_bootstrap_when_setting_exists():
    lookup_task = _load_task(
        REGISTRATION_DEFAULTS_TASKS,
        "Look up remote execution registration setting",
    )
    enable_task = _load_task(
        REGISTRATION_DEFAULTS_TASKS,
        "Enable remote execution bootstrap in registration commands",
    )
    lookup_setting = lookup_task["theforeman.foreman.setting_info"]
    enable_setting = enable_task["theforeman.foreman.setting"]

    assert lookup_task["register"] == REMOTE_EXECUTION_SETTING_REGISTER
    assert lookup_setting["name"] == enable_setting["name"] == REMOTE_EXECUTION_REGISTRATION_SETTING
    assert enable_setting["value"] is True

    assert _as_list(enable_task["when"]) == [
        f"{REMOTE_EXECUTION_SETTING_REGISTER}.setting is defined",
        f"{REMOTE_EXECUTION_SETTING_REGISTER}.setting is not none",
    ]
