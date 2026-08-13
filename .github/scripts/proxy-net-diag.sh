#!/bin/bash
# TEMPORARY DIAGNOSTIC SCRIPT - DO NOT MERGE
#
# Runs (as root, via `sudo bash`) on the `proxy` Vagrant VM in the
# "Tests Proxy Deployment" CI job, right after `foremanctl deploy-proxy`.
# Investigates whether the foreman-proxy container (network: host) can
# reach the postgresql container (network: foreman-db, isolated bridge,
# no published port) in the foreman-proxy-content flavor.
# See theforeman/foremanctl#611 for the motivating upstream PR.

echo "=== [DIAG] postgresql: NetworkSettings.Networks ==="
podman inspect postgresql --format '{{json .NetworkSettings.Networks}}' 2>&1 || echo "[DIAG] podman inspect postgresql networks: not available"

echo "=== [DIAG] postgresql: published ports (podman port) ==="
podman port postgresql 2>&1 || echo "[DIAG] podman port postgresql: no ports published or not available"

echo "=== [DIAG] foreman-proxy: HostConfig.NetworkMode ==="
podman inspect foreman-proxy --format '{{.HostConfig.NetworkMode}}' 2>&1 || echo "[DIAG] podman inspect foreman-proxy NetworkMode: not available"

echo "=== [DIAG] foreman-proxy: NetworkSettings.Networks ==="
podman inspect foreman-proxy --format '{{json .NetworkSettings.Networks}}' 2>&1 || echo "[DIAG] podman inspect foreman-proxy networks: not available"

echo "=== [DIAG] DNS resolution of 'postgresql' from inside foreman-proxy ==="
podman exec foreman-proxy getent hosts postgresql 2>&1 || echo "[DIAG] getent hosts postgresql: resolution failed or not available"

echo "=== [DIAG] Tools available inside foreman-proxy for connect test ==="
podman exec foreman-proxy sh -c 'command -v nc || command -v curl || command -v bash || echo none-found' 2>&1

try_connect() {
  local target="$1"
  local port="$2"
  echo "=== [DIAG] TCP connect attempt from inside foreman-proxy: ${target}:${port} ==="
  if podman exec foreman-proxy sh -c "command -v nc" >/dev/null 2>&1; then
    if podman exec foreman-proxy sh -c "nc -zv -w3 ${target} ${port}" 2>&1; then
      echo "[DIAG] RESULT: nc SUCCESS for ${target}:${port}"
    else
      echo "[DIAG] RESULT: nc FAILED for ${target}:${port}"
    fi
  elif podman exec foreman-proxy sh -c "command -v curl" >/dev/null 2>&1; then
    if podman exec foreman-proxy sh -c "curl -sv --connect-timeout 3 telnet://${target}:${port}" 2>&1; then
      echo "[DIAG] RESULT: curl telnet SUCCESS for ${target}:${port}"
    else
      echo "[DIAG] RESULT: curl telnet FAILED for ${target}:${port}"
    fi
  elif podman exec foreman-proxy sh -c "command -v bash" >/dev/null 2>&1; then
    if podman exec foreman-proxy sh -c "timeout 3 bash -c 'echo > /dev/tcp/${target}/${port}'" 2>&1; then
      echo "[DIAG] RESULT: /dev/tcp SUCCESS for ${target}:${port}"
    else
      echo "[DIAG] RESULT: /dev/tcp FAILED for ${target}:${port}"
    fi
  else
    echo "[DIAG] RESULT: no connect tool (nc/curl/bash) available inside foreman-proxy for ${target}:${port}"
  fi
}

for target in postgresql localhost 127.0.0.1; do
  try_connect "${target}" 5432
done

echo "=== [DIAG] Positive control: bridge-attached ephemeral container -> postgresql:5432 on foreman-db network ==="
PGIMAGE=$(podman inspect postgresql --format '{{.ImageName}}' 2>/dev/null)
echo "[DIAG] Using image for positive control: ${PGIMAGE:-unknown}"
if [ -n "${PGIMAGE}" ]; then
  if podman run --rm --network foreman-db "${PGIMAGE}" bash -c "command -v nc" >/dev/null 2>&1; then
    if podman run --rm --network foreman-db "${PGIMAGE}" bash -c "nc -zv -w3 postgresql 5432" 2>&1; then
      echo "[DIAG] RESULT: positive control SUCCESS via nc"
    else
      echo "[DIAG] RESULT: positive control FAILED via nc"
    fi
  else
    if podman run --rm --network foreman-db "${PGIMAGE}" bash -c "timeout 3 bash -c 'echo > /dev/tcp/postgresql/5432'" 2>&1; then
      echo "[DIAG] RESULT: positive control SUCCESS via /dev/tcp"
    else
      echo "[DIAG] RESULT: positive control FAILED via /dev/tcp"
    fi
  fi
else
  echo "[DIAG] RESULT: could not determine postgresql image for positive control"
fi

echo "=== [DIAG] END OF DIAGNOSTIC OUTPUT ==="
exit 0
