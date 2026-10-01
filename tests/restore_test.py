import subprocess
import time

import pytest

RESTORE_DIR = "/tmp/foremanctl-restore-test"

TARGET_INACTIVE_RETRIES = 60
TARGET_INACTIVE_DELAY = 2
RESTORE_COMPLETION_TIMEOUT = 1200

# Must stay stopped for the full restore window, then come back afterward.
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


@pytest.fixture(scope="module")
def restore_outcome(server, server_hostname, backup_for_restore):
    """Runs a real restore once; used below to check both the quiesce window and
    post-restore resume. Destructive - run against a disposable VM only."""
    restore_proc = subprocess.Popen(
        ['./foremanctl', 'restore', backup_for_restore, '--target-host', server_hostname, '--force'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        _wait_for_target_inactive(server)
        quiesced = {timer: server.service(timer).is_running for timer in QUIESCED_TIMERS}
        stdout, stderr = restore_proc.communicate(timeout=RESTORE_COMPLETION_TIMEOUT)
    except BaseException:
        # communicate() never kills on timeout, and a failed assertion above would
        # otherwise leave this running unattended - never leave it orphaned.
        restore_proc.kill()
        restore_proc.wait()
        raise

    return {
        'returncode': restore_proc.returncode,
        'stdout': stdout,
        'stderr': stderr,
        'quiesced': quiesced,
    }


def test_restore_command_succeeded(restore_outcome):
    assert restore_outcome['returncode'] == 0, (
        f"Restore should succeed, got rc={restore_outcome['returncode']}\n"
        f"stdout: {restore_outcome['stdout']}\nstderr: {restore_outcome['stderr']}"
    )


@pytest.mark.feature("iop")
def test_iop_timers_quiesced_during_restore(restore_outcome):
    still_running = [timer for timer, running in restore_outcome['quiesced'].items() if running]
    assert not still_running, (
        f"{still_running} still active while foreman.target was stopped for restore - "
        "they can fire mid-restore and race pg_restore"
    )


@pytest.mark.feature("iop")
def test_iop_timers_resumed_after_restore(server, restore_outcome):
    not_resumed = [timer for timer in QUIESCED_TIMERS if not server.service(timer).is_running]
    assert not not_resumed, f"{not_resumed} should be running again after the post-restore deploy"
