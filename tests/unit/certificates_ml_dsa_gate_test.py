import json
import os
import shutil
import subprocess

import pytest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROLE_DIR = os.path.abspath(os.path.join(TEST_DIR, '..', '..', 'src', 'roles', 'certificates'))
MAIN_TASKS = os.path.join(ROLE_DIR, 'tasks', 'main.yml')

PLAYBOOK = """
- hosts: localhost
  gather_facts: false
  connection: local
  vars:
    ansible_facts:
      os_family: RedHat
      distribution: RedHat
      distribution_major_version: '10'
      distribution_version: '{distribution_version}'
    certificates_enabled_algorithms: {enabled_algorithms}
    certificates_client_algorithm_type: '{client_algorithm_type}'
  tasks:
    - name: Run the certificates role gate
      ansible.builtin.import_tasks: "{main_tasks}"
"""


def run_gate(tmp_path, *, distribution_version, enabled_algorithms, client_algorithm_type='ML-DSA-65'):
    ansible_playbook = shutil.which('ansible-playbook')
    if ansible_playbook is None:
        pytest.skip('ansible-playbook is not available')

    playbook = tmp_path / 'playbook.yml'
    playbook.write_text(PLAYBOOK.format(
        distribution_version=distribution_version,
        enabled_algorithms=json.dumps(enabled_algorithms),
        client_algorithm_type=client_algorithm_type,
        main_tasks=MAIN_TASKS,
    ))
    return subprocess.run(
        [ansible_playbook, '-i', 'localhost,', '--tags', 'certificates_ml_dsa_gate', str(playbook)],
        text=True, capture_output=True,
    )


def test_rsa_server_with_default_mldsa_client_fails_on_old_rhel(tmp_path):
    """--add-certificate-algorithm=RSA alone must not bypass the gate via the default ML-DSA client cert."""
    result = run_gate(tmp_path, distribution_version='10.2', enabled_algorithms=['RSA'])
    assert result.returncode != 0, result.stdout
    assert 'ML-DSA' in result.stdout


def test_rsa_server_with_rsa_client_passes_on_old_rhel(tmp_path):
    result = run_gate(tmp_path, distribution_version='10.2', enabled_algorithms=['RSA'], client_algorithm_type='RSA')
    assert result.returncode == 0, result.stdout


def test_rsa_server_with_default_mldsa_client_passes_on_new_rhel(tmp_path):
    result = run_gate(tmp_path, distribution_version='10.3', enabled_algorithms=['RSA'])
    assert result.returncode == 0, result.stdout


def test_mldsa_server_fails_on_old_rhel(tmp_path):
    result = run_gate(tmp_path, distribution_version='10.2', enabled_algorithms=['ML-DSA-65'],
                       client_algorithm_type='ML-DSA-65')
    assert result.returncode != 0, result.stdout
