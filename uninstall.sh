#!/usr/bin/env bash
set -euo pipefail

APP_NAME="gmgn-forwarder"
SERVICE_NAME="${APP_NAME}.service"
RUN_USER="$(id -un)"
RUN_HOME="$(getent passwd "${RUN_USER}" | cut -d: -f6)"
INSTALL_DIR="${RUN_HOME}/${APP_NAME}"
SERVICE_TARGET="/etc/systemd/system/${SERVICE_NAME}"

log() {
  printf '[%s] %s\n' "${APP_NAME}" "$*"
}

fail() {
  printf '[%s] ERROR: %s\n' "${APP_NAME}" "$*" >&2
  exit 1
}

run_privileged() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

if [ -z "${RUN_HOME}" ] || [ "${RUN_HOME}" = "/" ]; then
  fail "Cannot determine a safe home directory for ${RUN_USER}."
fi

if [ "$(id -u)" -ne 0 ] && ! command -v sudo >/dev/null 2>&1; then
  printf '[%s] ERROR: sudo is required.\n' "${APP_NAME}" >&2
  exit 1
fi

if [ -f "${SERVICE_TARGET}" ]; then
  SERVICE_USER="$(sed -n 's/^User=//p' "${SERVICE_TARGET}" | head -n 1)"
  SERVICE_WORKDIR="$(sed -n 's/^WorkingDirectory=//p' "${SERVICE_TARGET}" | head -n 1)"

  if [ -n "${SERVICE_USER}" ] && [ "${SERVICE_USER}" != "${RUN_USER}" ]; then
    fail "Refusing to remove service owned by '${SERVICE_USER}' while running as '${RUN_USER}'."
  fi

  if [ -n "${SERVICE_WORKDIR}" ] && [ "${SERVICE_WORKDIR}" != "${INSTALL_DIR}" ]; then
    fail "Refusing to remove service for '${SERVICE_WORKDIR}' while target is '${INSTALL_DIR}'."
  fi
fi

log "Stopping service..."
run_privileged systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
run_privileged systemctl disable "${SERVICE_NAME}" 2>/dev/null || true

log "Removing systemd service..."
run_privileged rm -f "${SERVICE_TARGET}"
run_privileged systemctl daemon-reload
run_privileged systemctl reset-failed "${SERVICE_NAME}" 2>/dev/null || true

case "${INSTALL_DIR}" in
  "${RUN_HOME}"/gmgn-forwarder)
    log "Removing ${INSTALL_DIR}..."
    run_privileged rm -rf "${INSTALL_DIR}"
    ;;
  *)
    printf '[%s] ERROR: refusing to remove unexpected path: %s\n' "${APP_NAME}" "${INSTALL_DIR}" >&2
    exit 1
    ;;
esac

log "Uninstall complete."
