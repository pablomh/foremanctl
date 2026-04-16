import os
import uuid

import apypie
import paramiko
import py.path
import pytest
import testinfra
import yaml

from jinja2 import Environment, FileSystemLoader, select_autoescape


SSH_CONFIG='./.tmp/ssh-config'

# ---------------------------------------------------------------------------
# Rootless helpers
# ---------------------------------------------------------------------------

# Controls how run_as() switches to a non-root user. Set via environment
# variable so the testing method can be swapped without touching any test:
#
#   FOREMANCTL_RUN_AS_METHOD=runuser      (default) propagates exit codes
#   FOREMANCTL_RUN_AS_METHOD=machinectl  full login session, XDG auto-set,
#                                         but machinectl shell always exits 0
#   FOREMANCTL_RUN_AS_METHOD=systemd-run  runs in the user's systemd scope
RUN_AS_METHOD = os.environ.get("FOREMANCTL_RUN_AS_METHOD", "runuser")


def run_as(server, user, cmd):
    """Run *cmd* on *server* as *user*, using the configured RUN_AS_METHOD."""
    if RUN_AS_METHOD == "machinectl":
        # NOTE: machinectl shell always exits 0 regardless of the inner
        # command's exit code. Use result.stdout/stderr for assertions.
        return server.run(f"machinectl shell {user}@ /bin/bash -c '{cmd}'")
    elif RUN_AS_METHOD == "systemd-run":
        return server.run(
            f"systemd-run --user --machine={user}@ --wait --pipe -- /bin/bash -c '{cmd}'"
        )
    else:  # runuser (default)
        # Uses runuser -l to avoid inheriting the caller's CWD (which may be
        # inaccessible to the target user, e.g. /root).
        xdg = f"XDG_RUNTIME_DIR=/run/user/$(id -u {user})"
        escaped = cmd.replace("'", "'\\''")
        return server.run(
            f"runuser -l {user} -s /bin/bash -c 'export {xdg}; {escaped}'"
        )


def foremanctl_run(server, cmd):
    """Run *cmd* in the foremanctl user context via run_as."""
    return run_as(server, "foremanctl", cmd)


def foremanctl_exec(server, container, cmd="bash"):
    """Run *cmd* inside *container* via `foremanctl service exec`.

    Uses the foremanctl service tool rather than raw podman exec, so tests
    exercise the tool at the same time as verifying container behaviour.
    *cmd* is a single string passed directly to the container entrypoint.
    """
    return server.run(f"foremanctl service exec {container} {cmd}")


def service_is_running(server, name):
    """Return True if *name* is active according to `foremanctl service status`.

    Preferred over testinfra's server.service() for user-scope services
    because it exercises the operational tool at the same time.
    `systemctl status` exits 0 only when the unit is active.
    """
    return server.run(f"foremanctl service status {name}").rc == 0


def service_is_enabled(server, name):
    """Check if a user-scope service is enabled."""
    return run_as(server, "foremanctl", f"systemctl --user is-enabled {name}").rc == 0


def service_exists(server, name):
    """Check if a user-scope service unit exists."""
    # systemctl --user status exits 4 when the unit is not found
    return run_as(server, "foremanctl", f"systemctl --user status {name}").rc != 4


def service_start(server, name):
    """Start *name* via `foremanctl service start`. Returns the command result."""
    return server.run(f"foremanctl service start {name}")


def service_stop(server, name):
    """Stop *name* via `foremanctl service stop`. Returns the command result."""
    return server.run(f"foremanctl service stop {name}")


def service_restart(server, name):
    """Restart *name* via `foremanctl service restart`. Returns the command result."""
    return server.run(f"foremanctl service restart {name}")


def pytest_addoption(parser):
    parser.addoption("--certificate-source", action="store", default="default", choices=('default', 'installer'), help="Where to obtain certificates from")
    parser.addoption("--database-mode", action="store", default="internal", choices=('internal', 'external'), help="Whether the database is internal or external")


@pytest.fixture(scope="module")
def fixture_dir():
    return py.path.local(__file__).realpath() / '..' / 'fixtures'


@pytest.fixture(scope="module")
def server_hostname():
    return 'quadlet'


@pytest.fixture(scope="module")
def server_fqdn(server_hostname):
    return f'{server_hostname}.example.com'


@pytest.fixture(scope="module")
def client_hostname():
    return 'client'


@pytest.fixture(scope="module")
def client_fqdn(client_hostname):
    return f'{client_hostname}.example.com'


@pytest.fixture(scope="module")
def certificates(pytestconfig, server_fqdn):
    source = pytestconfig.getoption("certificate_source")
    env = Environment(loader=FileSystemLoader("."), autoescape=select_autoescape())
    template = env.get_template(f"./src/vars/{source}_certificates.yml")
    context = {'certificates_ca_directory': '/var/lib/foremanctl/certificates',
               'ansible_facts': {'fqdn': server_fqdn}}
    return yaml.safe_load(template.render(context))


@pytest.fixture(scope="module")
def database_mode(pytestconfig):
    return pytestconfig.getoption("database_mode")

@pytest.fixture(scope="module")
def server(server_hostname):
    yield testinfra.get_host(f'paramiko://{server_hostname}', sudo=True, ssh_config=SSH_CONFIG)


@pytest.fixture(scope="module")
def client(client_hostname):
    yield testinfra.get_host(f'paramiko://{client_hostname}', sudo=True, ssh_config=SSH_CONFIG)


@pytest.fixture(scope="module")
def database(database_mode, server):
    if database_mode == 'external':
        yield testinfra.get_host('paramiko://database', sudo=True, ssh_config=SSH_CONFIG)
    else:
        yield server


@pytest.fixture(scope="module")
def ssh_config(server_hostname):
    config = paramiko.SSHConfig.from_path(SSH_CONFIG)
    return config.lookup(server_hostname)


@pytest.fixture(scope="module")
def foremanapi(ssh_config, server_fqdn):
    api = apypie.ForemanApi(
        uri=f'https://{ssh_config["hostname"]}',
        username='admin',
        password='changeme',
        verify_ssl=False,
    )
    api._session.headers['Host'] = server_fqdn
    return api

@pytest.fixture
def organization(foremanapi):
    org = foremanapi.create('organizations', {'name': str(uuid.uuid4())})
    yield org
    foremanapi.delete('organizations', org)

@pytest.fixture
def product(organization, foremanapi):
    prod = foremanapi.create('products', {'name': str(uuid.uuid4()), 'organization_id': organization['id']})
    yield prod
    foremanapi.delete('products', prod)

@pytest.fixture
def yum_repository(product, organization, foremanapi):
    repo = foremanapi.create('repositories', {'name': str(uuid.uuid4()), 'product_id': product['id'], 'content_type': 'yum', 'url': 'https://fixtures.pulpproject.org/rpm-no-comps/'})
    wait_for_metadata_generate(foremanapi)
    yield repo
    foremanapi.delete('repositories', repo)

@pytest.fixture
def file_repository(product, organization, foremanapi):
    repo = foremanapi.create('repositories', {'name': str(uuid.uuid4()), 'product_id': product['id'], 'content_type': 'file', 'url': 'https://fixtures.pulpproject.org/file/'})
    wait_for_metadata_generate(foremanapi)
    yield repo
    foremanapi.delete('repositories', repo)

@pytest.fixture
def container_repository(product, organization, foremanapi):
    repo = foremanapi.create('repositories', {'name': str(uuid.uuid4()), 'product_id': product['id'], 'content_type': 'docker', 'url': 'https://quay.io/', 'docker_upstream_name': 'foreman/busybox-test'})
    wait_for_metadata_generate(foremanapi)
    yield repo
    foremanapi.delete('repositories', repo)

@pytest.fixture
def lifecycle_environment(organization, foremanapi):
    library = foremanapi.list('lifecycle_environments', 'name=Library', {'organization_id': organization['id']})[0]
    lce = foremanapi.create('lifecycle_environments', {'name': str(uuid.uuid4()), 'organization_id': organization['id'], 'prior_id': library['id']})
    yield lce
    foremanapi.delete('lifecycle_environments', lce)

@pytest.fixture
def content_view(organization, foremanapi):
    cv = foremanapi.create('content_views', {'name': str(uuid.uuid4()), 'organization_id': organization['id']})
    yield cv
    foremanapi.delete('content_views', cv)

@pytest.fixture
def activation_key(organization, foremanapi):
    ak = foremanapi.create('activation_keys', {'name': str(uuid.uuid4()), 'organization_id': organization['id']})
    yield ak
    foremanapi.delete('activation_keys', ak)

@pytest.fixture
def client_environment(activation_key, content_view, lifecycle_environment, yum_repository, organization, foremanapi):
    foremanapi.resource_action('repositories', 'sync', {'id': yum_repository['id']})
    foremanapi.update('content_views', {'id': content_view['id'], 'repository_ids': [yum_repository['id']]})
    foremanapi.resource_action('content_views', 'publish', {'id': content_view['id']})

    library = foremanapi.list('lifecycle_environments', 'name=Library', {'organization_id': organization['id']})[0]
    foremanapi.update('activation_keys', {'id': activation_key['id'], 'organization_id': organization['id'], 'environment_id': library['id'], 'content_view_id': content_view['id']})

    yield activation_key

    foremanapi.update('activation_keys', {'id': activation_key['id'], 'organization_id': organization['id'], 'environment_id': None, 'content_view_id': None})

    versions = foremanapi.list('content_view_versions', params={'content_view_id': content_view['id']})
    for version in versions:
        current_environment_ids = {environment['id'] for environment in version['environments']}
        for environment_id in current_environment_ids:
            foremanapi.resource_action('content_views', 'remove_from_environment', params={'id': content_view['id'], 'environment_id': environment_id})
        foremanapi.delete('content_view_versions', version)

def wait_for_tasks(foremanapi, search=None):
    tasks = foremanapi.list('foreman_tasks', search=search)
    for task in tasks:
        foremanapi.wait_for_task(task)

def wait_for_metadata_generate(foremanapi):
    wait_for_tasks(foremanapi, 'label = Actions::Katello::Repository::MetadataGenerate')
