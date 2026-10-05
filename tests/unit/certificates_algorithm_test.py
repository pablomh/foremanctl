import json
import os
import shutil
import subprocess
import tarfile

import pytest
import yaml

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROLE_DIR = os.path.abspath(os.path.join(TEST_DIR, '..', '..', 'src', 'roles', 'certificates'))
DEFAULTS_FILE = os.path.join(ROLE_DIR, 'defaults', 'main.yml')
VARS_DIR = os.path.join(ROLE_DIR, 'vars')
EXTRACT_FILE = os.path.join(ROLE_DIR, 'tasks', 'extract.yml')

PLAYBOOK = """
- hosts: localhost
  gather_facts: false
  connection: local
  tasks:
    - name: Load role defaults
      ansible.builtin.include_vars:
        file: "{defaults}"
    - name: Load role vars
      ansible.builtin.include_vars:
        file: "{vars_dir}/{{{{ certificates_primary_algorithm }}}}.yml"
    - name: Write resolved algorithm variables
      ansible.builtin.copy:
        content: "{{{{ {{'key_parameters': _certificates_key_parameters, 'key_usage': _certificates_key_usage}} | to_json }}}}"
        dest: "{output}"
        mode: '0644'
"""


def resolve_algorithm(tmp_path, algorithm=None):
    """Resolve the certificates role algorithm variables for the given algorithm."""
    ansible_playbook = shutil.which('ansible-playbook')
    if ansible_playbook is None:
        pytest.skip('ansible-playbook is not available')

    output = tmp_path / 'algorithm.json'
    playbook = tmp_path / 'playbook.yml'
    playbook.write_text(PLAYBOOK.format(defaults=DEFAULTS_FILE, vars_dir=VARS_DIR, output=output))

    command = [ansible_playbook, '-i', 'localhost,', str(playbook)]
    if algorithm is not None:
        command.extend(['-e', json.dumps({'certificates_algorithms': [algorithm]})])

    result = subprocess.run(command, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout

    return json.loads(output.read_text())


def test_default_algorithm_is_rsa():
    defaults = yaml.safe_load(open(DEFAULTS_FILE))
    assert defaults['certificates_default_algorithms'][0] == 'RSA'


def test_rsa_key_parameters_use_size(tmp_path):
    parameters = resolve_algorithm(tmp_path)['key_parameters']
    assert parameters['type'] == 'RSA'
    assert int(parameters['size']) == 4096
    assert 'curve' not in parameters


def test_ecc_key_parameters_use_curve(tmp_path):
    parameters = resolve_algorithm(tmp_path, 'ECC')['key_parameters']
    assert parameters['type'] == 'ECC'
    assert parameters['curve'] == 'secp384r1'
    assert 'size' not in parameters


@pytest.mark.parametrize('algorithm', ['ML-DSA-87'])
def test_ml_dsa_key_parameters_have_neither_size_nor_curve(tmp_path, algorithm):
    parameters = resolve_algorithm(tmp_path, algorithm)['key_parameters']
    assert parameters['type'] == algorithm
    assert 'size' not in parameters
    assert 'curve' not in parameters


def test_rsa_certificates_request_key_encipherment(tmp_path):
    assert resolve_algorithm(tmp_path)['key_usage'] == ['digitalSignature', 'keyEncipherment']


@pytest.mark.parametrize('algorithm', ['ECC', 'ML-DSA-87'])
def test_non_rsa_certificates_only_request_digital_signature(tmp_path, algorithm):
    assert resolve_algorithm(tmp_path, algorithm)['key_usage'] == ['digitalSignature']


def test_client_algorithm_defaults_to_primary(tmp_path):
    ansible_playbook = shutil.which('ansible-playbook')
    if ansible_playbook is None:
        pytest.skip('ansible-playbook is not available')

    output = tmp_path / 'client.json'
    playbook = tmp_path / 'client_playbook.yml'
    playbook.write_text("""
- hosts: localhost
  gather_facts: false
  connection: local
  tasks:
    - ansible.builtin.include_vars:
        file: "{defaults}"
    - ansible.builtin.copy:
        content: "{{{{ {{'client': certificates_client_algorithm_type,
                         'primary': certificates_primary_algorithm}} | to_json }}}}"
        dest: "{output}"
        mode: '0644'
""".format(defaults=DEFAULTS_FILE, output=output))

    command = [ansible_playbook, '-i', 'localhost,', str(playbook),
               '-e', json.dumps({'certificates_algorithms': ['ML-DSA-87', 'RSA']})]
    result = subprocess.run(command, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr

    resolved = json.loads(output.read_text())
    assert resolved['primary'] == 'ML-DSA-87'
    assert resolved['client'] == resolved['primary']


EXTRACT_PLAYBOOK = """
- hosts: localhost
  gather_facts: false
  connection: local
  tasks:
    - name: Load role defaults
      ansible.builtin.include_vars:
        file: "{defaults}"
    - name: Extract bundle and adopt the recorded algorithm order
      ansible.builtin.include_tasks: "{extract}"
    - name: Write resolved algorithms
      ansible.builtin.copy:
        content: "{{{{ {{'enabled': certificates_enabled_algorithms}} | to_json }}}}"
        dest: "{output}"
        mode: '0644'
"""


def build_bundle(tmp_path, enabled_order):
    staging = tmp_path / 'staging'
    for sub in ('certs', 'private', 'oauth'):
        (staging / sub).mkdir(parents=True, exist_ok=True)
    (staging / 'oauth' / 'foreman-oauth-consumer-key').write_text('key')
    if enabled_order is not None:
        (staging / 'algorithms.yaml').write_text(
            yaml.safe_dump({'certificates_enabled_algorithms': enabled_order}))

    bundle = tmp_path / 'bundle.tar.gz'
    with tarfile.open(bundle, 'w:gz') as tar:
        for sub in ('certs', 'private', 'oauth'):
            tar.add(staging / sub, arcname=sub)
        if enabled_order is not None:
            tar.add(staging / 'algorithms.yaml', arcname='algorithms.yaml')
    return bundle


def _has_gnu_tar():
    for name in ('gtar', 'tar'):
        exe = shutil.which(name)
        if exe and 'GNU tar' in subprocess.run([exe, '--version'], text=True, capture_output=True).stdout:
            return True
    return False


def adopt_enabled_algorithms(tmp_path, enabled_order):
    ansible_playbook = shutil.which('ansible-playbook')
    if ansible_playbook is None:
        pytest.skip('ansible-playbook is not available')
    if not _has_gnu_tar():
        pytest.skip('GNU tar is required to unarchive the bundle')

    bundle = build_bundle(tmp_path, enabled_order)
    ca_dir = tmp_path / 'consume'
    ca_dir.mkdir()
    output = tmp_path / 'enabled.json'
    playbook = tmp_path / 'extract_playbook.yml'
    playbook.write_text(EXTRACT_PLAYBOOK.format(defaults=DEFAULTS_FILE, extract=EXTRACT_FILE, output=output))

    extra = {
        'auth_bundle': str(bundle),
        'certificates_ca_directory': str(ca_dir),
        'certificates_oauth_directory': str(ca_dir / 'oauth'),
    }
    command = [ansible_playbook, '-i', 'localhost,', str(playbook), '-e', json.dumps(extra)]
    result = subprocess.run(command, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr

    return json.loads(output.read_text())['enabled']


def test_enabled_algorithms_order_preserved_pqc_first(tmp_path):
    assert adopt_enabled_algorithms(tmp_path, ['ML-DSA-87', 'RSA']) == ['ML-DSA-87', 'RSA']


def test_enabled_algorithms_order_preserved_classical_first(tmp_path):
    order = ['RSA', 'ML-DSA-65', 'ML-DSA-87']
    assert adopt_enabled_algorithms(tmp_path, order) == order


def test_enabled_algorithms_fallback_to_default_without_manifest(tmp_path):
    assert adopt_enabled_algorithms(tmp_path, None) == ['RSA', 'ML-DSA-65']
