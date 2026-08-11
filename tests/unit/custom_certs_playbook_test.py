import os

import yaml

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.abspath(os.path.join(TEST_DIR, '..', '..'))
CUSTOM_CERTS_METADATA = os.path.join(REPO_DIR, 'development', 'playbooks', 'custom-certs', 'metadata.obsah.yaml')
CUSTOM_CERTS_PLAYBOOK = os.path.join(REPO_DIR, 'development', 'playbooks', 'custom-certs', 'custom-certs.yaml')


def test_custom_certs_metadata_exposes_hostname():
    with open(CUSTOM_CERTS_METADATA, 'r') as metadata_file:
        metadata = yaml.safe_load(metadata_file)

    hostname = metadata["variables"]["hostname"]

    assert hostname["parameter"] == "--hostname"


def test_custom_certs_playbook_uses_default_fqdn_when_hostname_not_set():
    with open(CUSTOM_CERTS_PLAYBOOK, 'r') as playbook_file:
        playbook = yaml.safe_load(playbook_file)

    play = playbook[0]

    assert play["vars"]["certificates_hostnames"] == ["{{ hostname | default(ansible_facts['fqdn']) }}"]
