import os

from jinja2 import Environment
from jinja2 import FileSystemLoader

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.abspath(
    os.path.join(TEST_DIR, "..", "..", "src", "roles", "foreman_proxy", "templates")
)


def test_ansible_env_keeps_foreman_callback_enabled():
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=False)
    template = env.get_template("ansible.env.j2")

    rendered = template.render({"foreman_url": "https://quadlet.example.com"})

    assert 'export ANSIBLE_CALLBACKS_ENABLED="theforeman.foreman.foreman"' in rendered
    assert 'FOREMAN_CALLBACK_DISABLE' not in rendered
    assert 'export FOREMAN_URL="https://quadlet.example.com"' in rendered
