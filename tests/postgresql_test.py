import csv
import pytest

from conftest import foremanctl_run


def test_postgresql_service(database, user_service):
    assert user_service("postgresql").is_running


def test_postgresql_socket(database):
    socket = database.file("/var/lib/foremanctl/postgresql-socket/.s.PGSQL.5432")
    assert socket.exists


def test_postgresql_databases(database):
    result = foremanctl_run(database, "echo '\\\\l' | podman exec -i postgresql psql -U postgres")
    assert "foreman" in result.stdout
    assert "candlepin" in result.stdout
    assert "pulp" in result.stdout


def test_postgresql_users(database):
    result = foremanctl_run(database, "echo '\\\\du' | podman exec -i postgresql psql -U postgres")
    assert "foreman" in result.stdout
    assert "candlepin" in result.stdout
    assert "pulp" in result.stdout


def test_postgresql_password_encryption(database):
    result = foremanctl_run(database, "echo 'SHOW password_encryption;' | podman exec -i postgresql psql -U postgres")
    assert "scram-sha-256" in result.stdout

    result = foremanctl_run(database, "echo 'COPY (select * from pg_shadow) TO STDOUT (FORMAT CSV);' | podman exec -i postgresql psql -U postgres")

    reader = csv.reader(result.stdout.splitlines())
    for row in reader:
        assert ("SCRAM-SHA-256" in row[6])


def test_postgresql_missing_with_external(server, database_mode, user_service):
    if database_mode == 'internal':
        pytest.skip("Test only applies if database_mode=external")
    else:
        assert not user_service("postgresql").exists
