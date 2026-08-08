import os

from jinja2 import Environment
from jinja2 import FileSystemLoader

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.abspath(
    os.path.join(TEST_DIR, "..", "..", "src", "roles", "foreman", "templates")
)


def _render_settings(**context):
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=False)
    template = env.get_template("settings.yaml.j2")
    defaults = {
        "ansible_facts": {"domain": "example.com"},
        "foreman_name": "quadlet.example.com",
        "foreman_url": "https://quadlet.example.com",
        "foreman_aliases": [],
        "foreman_trusted_hosts": ["quadlet.example.com"],
        "foreman_rails_cache_url": "redis://valkey:6379/4",
        "foreman_oauth_consumer_key": "oauth-key",
        "foreman_oauth_consumer_secret": "oauth-secret",
        "httpd_external_authentication": "",
    }
    defaults.update(context)
    return template.render(defaults)


def test_foreman_settings_trust_proxy_callback_hosts():
    rendered = _render_settings(
        foreman_aliases=["foreman.example.com"],
        foreman_trusted_hosts=["quadlet.example.com", "proxy-ci.example.com"],
    )

    assert ":trusted_hosts:" in rendered
    assert "  - quadlet.example.com" in rendered
    assert "  - proxy-ci.example.com" in rendered
