import os

import yaml

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.abspath(os.path.join(TEST_DIR, '..', '..'))
CUSTOM_CERTS_METADATA = os.path.join(REPO_DIR, 'development', 'playbooks', 'custom-certs', 'metadata.obsah.yaml')
CUSTOM_CERTS_PLAYBOOK = os.path.join(REPO_DIR, 'development', 'playbooks', 'custom-certs', 'custom-certs.yaml')


def test_custom_certs_metadata_exposes_server_aliases():
    with open(CUSTOM_CERTS_METADATA, 'r') as metadata_file:
        metadata = yaml.safe_load(metadata_file)

    server_aliases = metadata["variables"]["server_aliases"]

    assert server_aliases["parameter"] == "--server-alias"
    assert server_aliases["action"] == "append_unique"
    assert server_aliases["type"] == "FQDN"


def test_custom_certs_playbook_passes_server_aliases_to_certificates_role():
    with open(CUSTOM_CERTS_PLAYBOOK, 'r') as playbook_file:
        playbook = yaml.safe_load(playbook_file)

    play = playbook[0]

    assert play["vars"]["certificates_server_aliases"] == "{{ server_aliases | default([]) }}"
