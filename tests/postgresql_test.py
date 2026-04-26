import csv
import pytest

from conftest import container_exec, service_is_running


def test_postgresql_service(database):
    assert service_is_running(database, "postgresql")


def test_postgresql_databases(database):
    result = container_exec(database, "postgresql", "psql -U postgres -c '\\l'")
    assert "foreman" in result.stdout
    assert "candlepin" in result.stdout
    assert "pulp" in result.stdout


def test_postgresql_users(database):
    result = container_exec(database, "postgresql", "psql -U postgres -c '\\du'")
    assert "foreman" in result.stdout
    assert "candlepin" in result.stdout
    assert "pulp" in result.stdout


def test_postgresql_password_encryption(database):
    result = container_exec(database, "postgresql", "psql -U postgres -c 'SHOW password_encryption'")
    assert "scram-sha-256" in result.stdout

    result = container_exec(database, "postgresql",
                             "bash -c \"echo 'COPY (select * from pg_shadow) TO STDOUT (FORMAT CSV);' | psql -U postgres\"")

    reader = csv.reader(result.stdout.splitlines())
    for row in reader:
        assert "SCRAM-SHA-256" in row[6]


def test_postgresql_missing_with_external(server, database_mode):
    if database_mode == 'internal':
        pytest.skip("Test only applies if database_mode=external")
    else:
        assert not service_is_running(server,
                          "postgresql")
