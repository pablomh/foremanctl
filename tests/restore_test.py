import subprocess
import time

import pytest

RESTORE_DIR = "/tmp/foremanctl-restore-test"

TARGET_INACTIVE_RETRIES = 60
TARGET_INACTIVE_DELAY = 2

# Must stay stopped for the full restore window.
QUIESCED_TIMERS = [
    "iop-service-vuln-vmaas-sync.timer",
    "iop-core-host-inventory-cleanup.timer",
    "iop-vex-download.timer",
    "iop-vuln-metadata-download.timer",
]

pytestmark = pytest.mark.slow


def _wait_for_target_inactive(server, target="foreman.target"):
    for _ in range(TARGET_INACTIVE_RETRIES):
        if not server.service(target).is_running:
            return
        time.sleep(TARGET_INACTIVE_DELAY)
    raise AssertionError(f"{target} did not stop within the expected window")


@pytest.fixture(scope="module")
def backup_for_restore(server, server_hostname):
    """A real backup to restore from - restore needs valid backup content on disk."""
    server.run(f"rm -rf {RESTORE_DIR}")
    result = server.run(f"mkdir -p {RESTORE_DIR}")
    assert result.rc == 0, f"Failed to create backup directory on VM: {result.stderr}"

    result = subprocess.run(
        ['./foremanctl', 'backup', RESTORE_DIR, '--target-host', server_hostname],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, \
        f"Backup for restore test should succeed, got rc={result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"

    find_result = server.run(f"ls -1 {RESTORE_DIR}")
    assert find_result.rc == 0, f"Backup directory should exist on VM: {find_result.stderr}"
    backup_dirs = [d for d in find_result.stdout.split('\n') if d.startswith('foreman-backup-')]
    assert len(backup_dirs) > 0, "Should have a timestamped backup directory to restore from"

    return f"{RESTORE_DIR}/{backup_dirs[0]}"


@pytest.mark.feature("iop")
@pytest.mark.xfail(
    strict=True,
    reason="IoP timers aren't scoped to foreman.target yet, so they keep running "
           "during a restore and can race pg_restore",
)
def test_iop_timers_quiesced_during_restore(server, server_hostname, backup_for_restore):
    """Destructive - run against a disposable VM only."""
    restore_proc = subprocess.Popen(
        ['./foremanctl', 'restore', backup_for_restore, '--target-host', server_hostname, '--force'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        _wait_for_target_inactive(server)

        still_running = [timer for timer in QUIESCED_TIMERS if server.service(timer).is_running]
        assert not still_running, (
            f"{still_running} still active while foreman.target is stopped for restore - "
            "they can fire mid-restore and race pg_restore"
        )
    finally:
        # Pre-fix, the restore can hang indefinitely - don't wait for it to finish.
        restore_proc.terminate()
        try:
            restore_proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            restore_proc.kill()
            restore_proc.wait(timeout=30)
