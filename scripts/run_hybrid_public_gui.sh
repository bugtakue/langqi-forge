#!/usr/bin/env bash
# Local diagnostic bridge only: test an already generated app with the legacy
# arm64 Playwright browser. This is not the current official Runner pipeline.
set -euo pipefail
umask 077

workspace="${1:?pass the prepared workspace path inside the browser container}"
run_label="${2:-first}"
if [[ ! "${run_label}" =~ ^[a-z0-9-]+$ ]]; then
  printf 'run label must contain only lowercase letters, digits and hyphens\n' >&2
  exit 2
fi
project="${workspace}/template"
tests="${workspace}/tests"
config="${tests}/hybrid.playwright.config.ts"
report="${workspace}/hybrid-playwright-${run_label}-report.json"
server_log="${workspace}/hybrid-backend-${run_label}.log"
test_log="${workspace}/hybrid-playwright-${run_label}-stderr.log"

for required in \
  "${project}/frontend/dist/index.html" \
  "${project}/backend/server.mjs" \
  "/opt/arcbench/node_modules/.bin/playwright" \
  "/harness/scripts/hybrid.playwright.config.ts"; do
  if [[ ! -e "${required}" ]]; then
    printf 'missing hybrid GUI input: %s\n' "${required}" >&2
    exit 2
  fi
done
if [[ -e "${report}" ]]; then
  printf 'refusing to overwrite an earlier hybrid GUI report: %s\n' "${report}" >&2
  exit 2
fi

# prepare-only copies the public specs but the full Runner normally creates
# this test package setup later. Keep this config separate from Runner files.
if [[ -e "${config}" ]]; then
  if ! cmp -s /harness/scripts/hybrid.playwright.config.ts "${config}"; then
    printf 'refusing to replace a different hybrid GUI config: %s\n' "${config}" >&2
    exit 2
  fi
else
  cp /harness/scripts/hybrid.playwright.config.ts "${config}"
fi
if [[ ! -e "${tests}/node_modules" ]]; then
  ln -s /opt/arcbench/node_modules "${tests}/node_modules"
fi
export FACTORY26_HYBRID_REPORT="${report}"
# The official local runner gives the unprivileged container user a writable
# HOME. Chromium's crashpad fails before any test when HOME defaults to /.
export HOME=/tmp/arcbench-home
mkdir -p "${HOME}"

# No model credentials are passed to this container. The generated backend may
# write its own application state inside the mounted workspace.
PORT=3000 HOST=127.0.0.1 node "${project}/backend/server.mjs" >"${server_log}" 2>&1 &
server_pid=$!
trap 'kill "${server_pid}" 2>/dev/null || true' EXIT

ready=0
for ((attempt = 1; attempt <= 80; attempt++)); do
  if curl --silent --fail --max-time 1 http://127.0.0.1:3000/api/health >/dev/null; then
    ready=1
    break
  fi
  if ! kill -0 "${server_pid}" 2>/dev/null; then
    printf 'generated backend exited before health check; see %s\n' "${server_log}" >&2
    exit 1
  fi
  sleep 0.25
done
if [[ "${ready}" != 1 ]]; then
  printf 'generated backend did not become healthy; see %s\n' "${server_log}" >&2
  exit 1
fi

cd "${tests}"
set +e
./node_modules/.bin/playwright test --config hybrid.playwright.config.ts >"${workspace}/hybrid-playwright-${run_label}-stdout.log" 2>"${test_log}"
status=$?
set -e
printf 'hybrid_gui_exit=%s report=%s stderr=%s\n' "${status}" "${report}" "${test_log}"
exit "${status}"
