#!/usr/bin/env bash
# Polls a GitHub Actions run for the moment any still-running job's
# "Setup upterm session" step opens its live SSH window, and prints the
# connection command as soon as it does.
#
# Usage: watch_upterm_window.sh <owner/repo> <run_id> [poll_seconds]
#
# Correct signal: a step named "Setup upterm session" with status
# "in_progress" on a job whose own status is still "in_progress". This is
# NOT the same as job.conclusion == "failure", which is only set after the
# job (and its upterm window) has already fully finished.

set -euo pipefail

REPO="${1:?usage: watch_upterm_window.sh <owner/repo> <run_id> [poll_seconds]}"
RUN_ID="${2:?usage: watch_upterm_window.sh <owner/repo> <run_id> [poll_seconds]}"
POLL_SECONDS="${3:-10}"

ALERTED=""

while true; do
  jobs=$(gh api "repos/${REPO}/actions/runs/${RUN_ID}/jobs?per_page=100" -q '.jobs[] | select(.status=="in_progress") | .id')

  for jid in $jobs; do
    if [[ "$ALERTED" == *" $jid "* ]]; then
      continue
    fi

    step_status=$(gh api "repos/${REPO}/actions/jobs/${jid}" \
      -q '.steps[]? | select(.name=="Setup upterm session") | .status' || true)

    if [[ "$step_status" == "in_progress" ]]; then
      echo "UPTERM_WINDOW_OPEN: job=${jid}"
      ssh_line=$(gh api "repos/${REPO}/actions/jobs/${jid}/logs" 2>/dev/null \
        | grep -m1 -oE 'ssh [A-Za-z0-9]+@uptermd\.upterm\.dev' || true)
      echo "SSH_COMMAND: ${ssh_line:-<not found yet, re-check logs manually>}"
      ALERTED="${ALERTED} ${jid} "
    fi
  done

  run_status=$(gh api "repos/${REPO}/actions/runs/${RUN_ID}" -q '.status')
  echo "poll $(date +%H:%M:%S) run_status=${run_status}"

  if [[ "$run_status" == "completed" ]]; then
    echo "RUN_COMPLETED"
    break
  fi

  sleep "${POLL_SECONDS}"
done
