---
name: ci-upterm-live-debug
description: >-
  Connect to a live GitHub Actions runner via SSH (upterm/tmate) to debug this
  repo's CI jobs interactively, or analyze a completed job's logs/artifacts
  post-mortem when live access is no longer possible. Use when a CI job fails
  and you want a shell on the actual runner, when you want proactive live
  access to a passing job (e.g. to compare state across matrix legs), or when
  investigating a CI failure after the run has already finished.
---

# CI upterm live debug

This repo's `.github/workflows/test.yml` jobs each end with an
`owenthereal/action-upterm@v1` step that opens an SSH-accessible shell
directly on the GitHub Actions runner. Two distinct scenarios need different
approaches: **live** access (job still running) vs **post-mortem** (job
already completed — live access is permanently impossible).

## Key facts (don't relearn these)

- By default the upterm step has `if: ${{ failure() }}` — it only starts
  *after* a prior step in that job has already failed. You cannot get a shell
  on a job that is currently passing/healthy unless the workflow is modified
  (see "Proactive access" below).
- `wait-timeout-minutes: 5` (or whatever the workflow sets) only governs "shut
  down if nobody ever connects". Once connected, there is no further timeout
  from this setting — you can explore for as long as you want.
- `limit-access-to-actor: true` authorizes only SSH keys registered on the
  GitHub account that triggered the run (fetched from
  `https://github.com/<actor>.keys`). If you can already `git push` to the
  fork over SSH, the same local key/agent will work for connecting.
- The job's overall `status` stays `in_progress` for the entire duration the
  upterm step is waiting/connected. It only becomes `completed` once that step
  itself finishes (timeout, or you let it go). **Do not poll for
  `conclusion == "failure"`** — that field is only set *after* the job (and
  its upterm window) has already fully finished, i.e. too late.
- Once a job shows `status: completed`, the runner VM is destroyed
  immediately. There is no way back in — "connecting" to a finished job's
  printed SSH command will always fail. That's expected, not a bug.
- Once connected, run `sudo touch /continue` to let the job proceed past the
  upterm step to its remaining steps. If the upterm step is the last one, you
  can just disconnect/let it idle to the timeout instead.

## Detecting the live window and connecting

Use `scripts/watch_upterm_window.sh <owner/repo> <run_id>` — it polls each
still-`in_progress` job in the run for a step named "Setup upterm session"
transitioning to `in_progress` (the real live-window signal), then extracts
the `ssh ...@uptermd.upterm.dev` command straight from that job's live log.
It prints `UPTERM_WINDOW_OPEN: job=<id>` and `SSH_COMMAND: ssh ...` the moment
this happens — run it in the background and watch for that output.

```bash
.cursor/skills/ci-upterm-live-debug/scripts/watch_upterm_window.sh pablomh/foremanctl <run_id>
```

Then connect with the printed command, e.g.:

```bash
ssh T6XX3688lgl4zpmBzsGQ@uptermd.upterm.dev
```

## Proactive access (connect even when the job isn't failing)

To get a shell on a job regardless of pass/fail — e.g. to interactively
compare live state across two matrix legs (like `centos/stream9` vs
`centos/stream10`) — you need a temporary workflow change, because:

1. This repo's `on:` trigger only fires on `push` to `master`/`*-stable`, or
   on `pull_request`. Pushing a plain feature/scratch branch triggers
   nothing — you must open a PR (even within the same fork) to get a run.
2. Editing the real branch you're debugging would cancel its in-flight CI run
   (the workflow's `concurrency` group is keyed on `github.ref_name`, with
   `cancel-in-progress: true`). Always do this on a **separate scratch
   branch**, based off the branch/commit you actually want to inspect.

Steps:

1. `git checkout -b debug/<short-description>` from the commit you want to
   inspect (so the real topology/code under test is preserved).
2. In `.github/workflows/test.yml`, on the relevant job's `Setup upterm
   session` step, change `if: ${{ failure() }}` to `if: ${{ always() }}` and
   raise `wait-timeout-minutes` (e.g. to `20`) to give yourself a comfortable
   connect window.
3. Optionally trim the job's `matrix` down to only the legs you care about —
   saves CI minutes and gets you a shell faster.
4. Commit clearly marked `DEBUG ONLY` (so nobody mistakes it for a real
   change), push to the fork, then open a PR **within the fork** (`--repo
   <fork>`, base = the real branch, head = the scratch branch) — this is what
   actually triggers the run, per point 1 above.
5. Run the watcher script against the resulting run.
6. When done: close the throwaway PR and delete the scratch branch
   (`git push <fork> --delete debug/<short-description>`).

## Post-mortem (job already completed — no live shell possible)

Once `status: completed`, don't waste time trying to connect — instead pull
recorded evidence:

- Full job log: `gh run view --job <job_id> --repo <owner/repo> --log` (only
  works once the *whole run* has finished) or
  `gh api repos/<owner/repo>/actions/jobs/<job_id>/logs` (works as soon as
  that individual job is done, even if the run overall is still going).
- Uploaded artifacts (this repo uploads `sosreport-*`, `diagnostics-*`,
  `smoker-*` per matrix leg regardless of pass/fail):
  `gh api repos/<owner/repo>/actions/runs/<run_id>/artifacts` to list, then
  `gh run download <run_id> --repo <owner/repo> -n <artifact-name> -D <dest>`.
- Step-level timing/status for reconstructing what happened when:
  `gh api repos/<owner/repo>/actions/jobs/<job_id> -q '.steps[] |
  {name,status,conclusion,started_at,completed_at}'`.
