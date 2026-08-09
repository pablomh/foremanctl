import datetime
import os
import subprocess
import uuid
from functools import cached_property

import apypie
import paramiko
import py.path
import pytest
import requests
import testinfra
import yaml
from jinja2 import Environment
from jinja2 import FileSystemLoader
from jinja2 import select_autoescape
from requests.adapters import HTTPAdapter

SSH_CONFIG = './.tmp/ssh-config'
OBSAH_STATE = os.environ.get('OBSAH_STATE', '.var/lib/foremanctl')
PARAMETERS_FILE = os.path.join(OBSAH_STATE, 'parameters.yaml')
FLAVOR_TESTS_DIR = py.path.local(__file__).dirpath() / 'flavor'
FOREMAN_PROXY_PORT = 8443

# --- BEGIN TEMPORARY DIAGNOSTIC INSTRUMENTATION -----------------------------------------
# Investigating a possible SSH key identity mismatch: is the smart proxy whose pubkey
# Foreman embeds into a generated host registration/bootstrap script (when
# host_registration_remote_execution is enabled) actually the SAME smart proxy that later
# executes remote-execution SSH jobs against that host? This is purely additive
# logging/diagnostics; it does not change any fixture's setup/teardown behavior or any
# test's pass/fail outcome. Safe to delete this block (and its call sites, search for
# "DIAGNOSTIC INSTRUMENTATION") once the investigation concludes.
DIAGNOSTIC_ARTIFACT_PATH = py.path.local(__file__).dirpath() / '..' / 'diagnostics' / 'ssh_key_identity_investigation.log'


def _record_diagnostic(capsys, label, content):
    """Print (bypassing pytest's output capture, so it shows up in CI logs for both
    passing and failing tests) and append to a local artifact file, clearly labelled so
    it is trivially greppable."""
    block = f"=== DIAGNOSTIC[{label}] ===\n{content}\n=== END DIAGNOSTIC[{label}] ===\n"
    with capsys.disabled():
        print(f"\n{block}")
    try:
        DIAGNOSTIC_ARTIFACT_PATH.dirpath().ensure(dir=True)
        with open(str(DIAGNOSTIC_ARTIFACT_PATH), 'a', encoding='utf-8') as fh:
            fh.write(block + "\n")
    except OSError:
        pass
# --- END TEMPORARY DIAGNOSTIC INSTRUMENTATION -------------------------------------------


# --- BEGIN TEMPORARY DIAGNOSTIC INSTRUMENTATION -----------------------------------------
# Investigating an intermittent, CI-only flake on the centos/stream10 + iop:enabled matrix
# lane: `test_foreman_reaches_proxy_via_registration_url` occasionally times out reaching
# the `foreman-proxy` container's published port (8443) via its public FQDN, and Ansible
# REX tests occasionally time out around the same time. Leading (unconfirmed) hypothesis is
# a netavark 2.0 stale-DNAT-rule bug (containers/podman#27516) triggered by container
# recreation, but a synthetic minimal repro failed to reproduce it. This hook captures the
# real nftables/network/container state at the exact moment ANY test fails (not just the
# known-flaky ones, since we don't know in advance which test will next expose it), so a
# genuine CI recurrence can be analyzed with real evidence instead of a synthetic guess.
# This is purely additive: it only runs extra read-only diagnostic commands after a test has
# already failed, and it is wrapped in broad exception handling so a bug in the
# instrumentation itself can never mask/alter the real failure or fail an otherwise-passing
# test. Safe to delete this block (and its hook, search for "DIAGNOSTIC INSTRUMENTATION")
# once the investigation concludes.
NETWORK_DIAGNOSTIC_ARTIFACT_PATH = py.path.local(__file__).dirpath() / '..' / 'diagnostics' / 'network_state_at_failure.log'
NETWORK_DIAGNOSTIC_NETWORKS = ('foreman-app', 'foreman-proxy')


def _run_diagnostic_command(server, label, command):
    """Run a single diagnostic command, tolerating any failure so one bad command can never
    prevent the rest of the capture from running."""
    try:
        result = server.run(command)
        return f"$ {command}\n(rc={result.rc})\n{result.stdout}{result.stderr}"
    except Exception as exc:  # noqa: BLE001 - diagnostics must never break the test run
        return f"$ {command}\n<command failed to execute: {exc!r}>"


def _capture_network_state_at_failure(item, server):
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    sections = [f"nodeid={item.nodeid} timestamp={timestamp}"]

    commands = [
        ("nftables ruleset (with handles)", "nft -a list ruleset"),
        ("iptables-save (legacy-shim visibility)", "iptables-save -c"),
        ("podman ps -a (recreate/restart history)",
         "podman ps -a --format '{{.Names}}\t{{.Status}}\t{{.CreatedAt}}'"),
        ("foreman container network settings",
         "podman inspect foreman --format '{{json .NetworkSettings.Networks}}' 2>&1"),
        ("foreman-proxy container network settings",
         "podman inspect foreman-proxy --format '{{json .NetworkSettings.Networks}}' 2>&1"),
    ]
    for network in NETWORK_DIAGNOSTIC_NETWORKS:
        commands.append((f"podman network inspect {network}", f"podman network inspect {network} 2>&1"))
    commands.extend([
        ("foreman-proxy container logs (last 10m)",
         "journalctl -u foreman-proxy --since '-10 minutes' --no-pager"),
        ("aardvark-dns log lines (last 10m, host-wide)",
         "journalctl --since '-10 minutes' --no-pager | grep -i aardvark || echo '<no aardvark-dns log lines found>'"),
        # Two real occurrences (see git history around this hook) ruled out the initial
        # stale-DNAT-rule hypothesis: a single correct rule, no recent restart, proxy healthy
        # throughout. The remaining open hypotheses are conntrack pressure and CPU/IO
        # scheduling contention on the (nested-virtualization) CI runner. These captures target
        # exactly that, since neither was available in the earlier occurrences' evidence.
        ("CPU pressure (PSI, may not exist on all kernels)",
         "cat /proc/pressure/cpu 2>&1 || echo '<PSI not available on this kernel>'"),
        ("IO pressure (PSI, may not exist on all kernels)",
         "cat /proc/pressure/io 2>&1 || echo '<PSI not available on this kernel>'"),
        ("conntrack table usage vs limit",
         "echo \"count=$(cat /proc/sys/net/netfilter/nf_conntrack_count 2>&1)\" "
         "\"max=$(cat /proc/sys/net/netfilter/nf_conntrack_max 2>&1)\""),
        ("conntrack drop/error counters (per-CPU)",
         "cat /proc/net/stat/nf_conntrack 2>&1 || echo '<not available>'"),
        ("network interface error/drop counters",
         "ip -s link show"),
        ("load average / uptime",
         "uptime"),
    ])

    for label, command in commands:
        sections.append(f"--- {label} ---\n{_run_diagnostic_command(server, label, command)}")

    try:
        fqdn = server.run("hostname -f").stdout.strip()
        if fqdn:
            curl_command = (
                "podman exec foreman curl --silent --show-error --connect-timeout 5 --max-time 10 "
                f"-o /dev/null -w '%{{http_code}} %{{time_total}}\\n' https://{fqdn}:8443/v2/features"
            )
            sections.append(f"--- live curl repro (foreman -> foreman-proxy:8443) ---\n"
                             f"{_run_diagnostic_command(server, 'live curl repro', curl_command)}")
    except Exception as exc:  # noqa: BLE001 - skip this specific capture rather than risk flakiness
        sections.append(f"--- live curl repro (foreman -> foreman-proxy:8443) ---\n<skipped: {exc!r}>")

    block = "\n\n".join(sections)
    NETWORK_DIAGNOSTIC_ARTIFACT_PATH.dirpath().ensure(dir=True)
    with open(str(NETWORK_DIAGNOSTIC_ARTIFACT_PATH), 'a', encoding='utf-8') as fh:
        fh.write(f"===== NETWORK STATE AT FAILURE: {item.nodeid} ({timestamp}) =====\n{block}\n"
                  f"===== END NETWORK STATE AT FAILURE: {item.nodeid} =====\n\n")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    try:
        report = outcome.get_result()
        if report.when != 'call' or not report.failed:
            return
        server = item.funcargs.get('server')
        if server is None:
            return
        _capture_network_state_at_failure(item, server)
    except Exception:  # noqa: BLE001 - a diagnostic-capture bug must never affect test results
        pass
# --- END TEMPORARY DIAGNOSTIC INSTRUMENTATION -------------------------------------------


class UserParameters:
    def __init__(self, config):
        self._config = config

    @cached_property
    def features(self):
        # foremanctl outputs
        # FEATURE                   STATE               DESCRIPTION
        # $feature                  enabled/available   $description
        output = subprocess.check_output(['./foremanctl', 'features'], cwd=self._config.rootdir,
                                         universal_newlines=True)
        lines = output.splitlines(keepends=False)
        # feature, status, description
        return [line.split(None, 2) for line in lines[1:]]

    @cached_property
    def available_features(self):
        return set(feature for feature, _status, _desc in self.features)

    @cached_property
    def enabled_features(self):
        return set(feature for feature, status, _desc in self.features if status == 'enabled')

    @cached_property
    def flavor(self):
        with open(PARAMETERS_FILE) as f:
            params = yaml.safe_load(f)
        return params.get('flavor', 'katello')


def pytest_addoption(parser):
    parser.addoption("--server-hostname", action="store", default="quadlet", help="Hostname of the server VM to test against")


@pytest.fixture(scope="module")
def flavor(pytestconfig):
    return pytestconfig.user_parameters.flavor


@pytest.fixture(scope="module")
def enabled_features(pytestconfig):
    return pytestconfig.user_parameters.enabled_features


@pytest.fixture(scope="module")
def available_features(pytestconfig):
    return pytestconfig.user_parameters.available_features


@pytest.fixture(scope="module")
def fixture_dir():
    return py.path.local(__file__).realpath() / '..' / 'fixtures'


@pytest.fixture(scope="module")
def server_hostname(pytestconfig):
    return pytestconfig.getoption("server_hostname")


@pytest.fixture(scope="module")
def server_fqdn(server):
    return server.check_output('hostname -f')


@pytest.fixture(scope="module")
def client_hostname():
    return 'client'


@pytest.fixture(scope="module")
def client_fqdn(client):
    return client.check_output('hostname -f')


@pytest.fixture(scope="module")
def certificates(server_fqdn):
    env = Environment(loader=FileSystemLoader("."), autoescape=select_autoescape())
    template = env.get_template("./src/vars/certificates.yml")
    context = {'ansible_facts': {'fqdn': server_fqdn}}
    # we have vars that refer to other vars, so load them once and then re-render the template
    context.update(yaml.safe_load(template.render(context)))
    return yaml.safe_load(template.render(context))


@pytest.fixture(scope="module")
def obsah_params():
    with open(PARAMETERS_FILE) as f:
        params = yaml.safe_load(f)
    return params


@pytest.fixture(scope="module")
def certificate_source(obsah_params):
    return obsah_params.get('certificates_source', 'default')


@pytest.fixture(scope="module")
def custom_certificates(certificate_source):
    if certificate_source != 'custom_server':
        pytest.skip("Only applies to custom certificate deployments")


@pytest.fixture(scope="module")
def default_certificates(certificate_source):
    if certificate_source == 'custom_server':
        pytest.skip("Only applies to non-custom certificate deployments")


@pytest.fixture(scope="module")
def quadlet_client_certificate():
    # this intentionally uses get_paramiko_host directly, as we want the cert of the quadlet box
    # not the one "server" points at, as that can be the proxy
    quadlet = get_paramiko_host('quadlet')
    hostname = quadlet.run("hostname -f").stdout.strip()
    cert = quadlet.file(f"/var/lib/foremanctl/certs/certs/{hostname}-client.crt").content_string
    key = quadlet.file(f"/var/lib/foremanctl/certs/private/{hostname}-client.key").content_string
    return (cert, key)


@pytest.fixture(scope="module")
def database_mode(obsah_params):
    return obsah_params.get('database_mode', 'internal')


def get_paramiko_host(hostname):
    return testinfra.get_host(f'paramiko://{hostname}', sudo=True, ssh_config=SSH_CONFIG)


@pytest.fixture(scope="module")
def server(server_hostname):
    yield get_paramiko_host(server_hostname)


@pytest.fixture(scope="module")
def client(client_hostname):
    yield get_paramiko_host(client_hostname)


@pytest.fixture
def remote_execution_authorized_proxy_key(server, client, foremanapi, capsys):
    # --- BEGIN TEMPORARY DIAGNOSTIC INSTRUMENTATION (see top of file) ---
    # Capture evidence BEFORE this fixture injects the foreman-proxy key manually below,
    # so we can see what state the client and Foreman were actually in beforehand.
    client_authorized_keys_before = client.run(
        "cat /root/.ssh/authorized_keys 2>/dev/null || echo '<authorized_keys missing or empty>'"
    ).stdout
    _record_diagnostic(capsys, "CLIENT_AUTHORIZED_KEYS_BEFORE_FIXTURE", client_authorized_keys_before)

    foreman_proxy_container_pubkey_diag = server.run(
        "podman exec foreman-proxy cat /usr/share/foreman-proxy/.ssh/id_rsa_foreman_proxy.pub 2>&1"
    ).stdout
    _record_diagnostic(capsys, "FOREMAN_PROXY_CONTAINER_PUBKEY", foreman_proxy_container_pubkey_diag)

    # Does the main `foreman` container/host have any SSH keypair of its own that could be
    # (mis)used for registration/remote-execution purposes, distinct from foreman-proxy's key?
    foreman_container_ssh_keys = server.run(
        "podman exec foreman sh -c "
        "\"find /usr/share/foreman /root/.ssh -iname 'id_rsa*' 2>/dev/null "
        "-exec sh -c 'echo ---{}---; cat {}' \\;\" 2>&1"
    ).stdout
    _record_diagnostic(capsys, "FOREMAN_CONTAINER_SSH_KEYS", foreman_container_ssh_keys or '<none found>')

    server_host_ssh_keys = server.run(
        "find /usr/share/foreman /root/.ssh -iname 'id_rsa*' 2>/dev/null"
    ).stdout
    _record_diagnostic(capsys, "SERVER_HOST_SSH_KEYS", server_host_ssh_keys or '<none found outside containers>')

    try:
        smart_proxies = foremanapi.list('smart_proxies', params={'per_page': 100})
        # remote_execution_pubkey/remote_execution_ca_pubkey are the smart_proxies.pubkey /
        # ca_pubkey DB columns (foreman_remote_execution's SmartProxyExtensions#pubkey with
        # refresh: false) -- i.e. exactly what Host#remote_execution_ssh_keys reads when
        # deciding which key(s) to embed into a generated registration script. If this is
        # nil/blank for the proxy that actually executes SSH REX jobs, NO key gets embedded
        # for it (this is distinct from "the wrong key gets embedded").
        smart_proxies_summary = "\n".join(
            "id={id} name={name!r} url={url!r} features={features} "
            "remote_execution_pubkey={pubkey!r} remote_execution_ca_pubkey={ca_pubkey!r}".format(
                id=proxy.get('id'),
                name=proxy.get('name'),
                url=proxy.get('url'),
                features=[f.get('name') for f in proxy.get('features', [])],
                pubkey=proxy.get('remote_execution_pubkey'),
                ca_pubkey=proxy.get('remote_execution_ca_pubkey'),
            )
            for proxy in smart_proxies
        ) or '<no smart proxies returned>'
    except Exception as exc:  # noqa: BLE001 - diagnostics must never break the fixture
        smart_proxies_summary = f"<failed to fetch smart_proxies: {exc!r}>"
    _record_diagnostic(capsys, "SMART_PROXIES_LIST", smart_proxies_summary)
    # --- END TEMPORARY DIAGNOSTIC INSTRUMENTATION ---

    proxy_public_key = server.check_output(
        "podman exec foreman-proxy cat /usr/share/foreman-proxy/.ssh/id_rsa_foreman_proxy.pub"
    ).strip()

    client.run_test(
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        "ssh_dir = Path('/root/.ssh')\n"
        "ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)\n"
        "authorized_keys = ssh_dir / 'authorized_keys'\n"
        "authorized_keys.touch()\n"
        "authorized_keys.chmod(0o600)\n"
        f"proxy_public_key = {proxy_public_key!r}\n"
        "lines = authorized_keys.read_text().splitlines()\n"
        "if proxy_public_key not in lines:\n"
        "    with authorized_keys.open('a', encoding='utf-8') as fh:\n"
        "        fh.write(proxy_public_key + '\\n')\n"
        "PY"
    )

    yield

    client.run(
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        "authorized_keys = Path('/root/.ssh/authorized_keys')\n"
        f"proxy_public_key = {proxy_public_key!r}\n"
        "if authorized_keys.exists():\n"
        "    filtered = [line for line in authorized_keys.read_text().splitlines() if line != proxy_public_key]\n"
        "    if filtered:\n"
        "        authorized_keys.write_text('\\n'.join(filtered) + '\\n', encoding='utf-8')\n"
        "    else:\n"
        "        authorized_keys.unlink()\n"
        "PY"
    )


@pytest.fixture(scope="module")
def database(database_mode, server):
    if database_mode == 'external':
        yield get_paramiko_host('database')
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
    cve = foremanapi.list('content_view_environments', params={'organization_id': organization['id'], 'environment_id': library['id'], 'content_view_id': content_view['id']})[0]
    foremanapi.update('activation_keys', {'id': activation_key['id'], 'organization_id': organization['id'], 'content_view_environment_ids': [cve['id']]})

    yield activation_key

    foremanapi.update('activation_keys', {'id': activation_key['id'], 'organization_id': organization['id'], 'content_view_environment_ids': []})

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


def assert_container_resolves_hostname(server, container_name, hostname):
    dns_result = server.run(f"podman exec {container_name} getent hosts {hostname}")
    assert dns_result.succeeded, f"DNS-resolvable host {hostname} not found from {container_name} container"


def assert_container_resolves_server_fqdn(server, container_name, server_fqdn):
    assert_container_resolves_hostname(server, container_name, server_fqdn)


def pytest_configure(config):
    config.addinivalue_line("markers", "feature(name): mark a test as requiring a feature")

    config.user_parameters = UserParameters(config)


def pytest_collection_modifyitems(config, items):
    active_flavor = config.user_parameters.flavor
    active_flavor_dir = FLAVOR_TESTS_DIR / active_flavor

    deselected = []
    selected = []
    for item in items:
        test_path = py.path.local(item.fspath)
        if test_path.relto(FLAVOR_TESTS_DIR):
            if not test_path.relto(active_flavor_dir):
                deselected.append(item)
                continue
        selected.append(item)

    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected

    feature_dir = config.rootdir / 'tests' / 'feature'
    for item in items:
        try:
            rel_path = item.path.relative_to(feature_dir)
        except ValueError:
            # Not in the features directory
            pass
        else:
            feature = rel_path.parts[0]
            item.add_marker(pytest.mark.feature(feature))


def pytest_runtest_setup(item):
    feature_markers = set(mark.args[0] for mark in item.iter_markers(name="feature"))
    if feature_markers:
        invalid_features = feature_markers - item.config.user_parameters.available_features
        if invalid_features:
            raise pytest.PytestConfigWarning(f"Invalid feature(s) {invalid_features!r} on {item}")
        missing = feature_markers - item.config.user_parameters.enabled_features
        if missing:
            pytest.skip(f"test requires feature(s) {missing!r}")


class ResolveAdapter(HTTPAdapter):
    def __init__(self, target_ip, *args, **kwargs):
        self.target_ip = target_ip
        super().__init__(*args, **kwargs)

    def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
        conn = super().get_connection_with_tls_context(request, verify, proxies, cert)

        # Override the host to point to your target IP
        # This forces the socket to open to target_ip instead of the URL's domain
        conn.host = self.target_ip

        return conn


@pytest.fixture(scope="module")
def local_request(ssh_config, server_fqdn):
    session = requests.Session()
    adapter = ResolveAdapter(target_ip=ssh_config["hostname"])
    session.mount(f"http://{server_fqdn}", adapter)
    session.mount(f"https://{server_fqdn}", adapter)
    return session


@pytest.fixture(scope="module")
def proxy_base_url(server_fqdn):
    return f"https://{server_fqdn}:{FOREMAN_PROXY_PORT}"


@pytest.fixture(scope="module")
def curl_request(server, certificates, quadlet_client_certificate, server_fqdn):
    cert, key = quadlet_client_certificate
    server.run(f"echo '{cert}' > /tmp/quadlet.crt")
    server.run(f"echo '{key}' > /tmp/quadlet.key")

    def _request(path, base_url=None, method=None, data=None, headers=None, return_body=False):
        url = f"{base_url or f'https://{server_fqdn}'}/{path}"
        curl_opts = (
            f"--cacert {certificates['server_ca_certificate']} "
            f"--cert /tmp/quadlet.crt "
            f"--key /tmp/quadlet.key "
            f"--silent "
        )
        if not return_body:
            curl_opts += "--write-out '%{http_code}' --output /dev/null "
        if method:
            curl_opts += f"-X {method} "
        if data:
            curl_opts += f"-d '{data}' "
        if headers:
            for key, value in headers.items():
                curl_opts += f"--header '{key}: {value}' "
        return server.run(f"curl {curl_opts}{url}")
    return _request


@pytest.fixture
def foreman_plugins(foremanapi):
    return [plugin['name'] for plugin in foremanapi.list('plugins')]
