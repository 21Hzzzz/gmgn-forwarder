#!/usr/bin/env bash
set -euo pipefail

APP_NAME="gmgn-forwarder"
SERVICE_NAME="${APP_NAME}.service"
RUN_USER="$(id -un)"
RUN_GROUP="$(id -gn)"
RUN_HOME="$(getent passwd "${RUN_USER}" | cut -d: -f6)"
INSTALL_DIR="${RUN_HOME}/${APP_NAME}"
REPO_URL="https://github.com/21Hzzzz/gmgn-forwarder.git"
UV_BIN="${RUN_HOME}/.local/bin/uv"
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

as_run_user() {
  env HOME="${RUN_HOME}" "$@"
}

if [ "${REPO_URL}" = "https://github.com/YOUR_NAME/gmgn-forwarder.git" ]; then
  fail "Edit REPO_URL in install.sh before running this installer."
fi

if [ -z "${RUN_HOME}" ] || [ "${RUN_HOME}" = "/" ]; then
  fail "Cannot determine a safe home directory for ${RUN_USER}."
fi

if [ ! -d "${RUN_HOME}" ]; then
  fail "Home directory does not exist: ${RUN_HOME}."
fi

if [ "$(id -u)" -ne 0 ] && ! command -v sudo >/dev/null 2>&1; then
  fail "sudo is required."
fi

if ! command -v apt-get >/dev/null 2>&1; then
  fail "This installer targets Ubuntu/Debian systems with apt-get."
fi

if ! command -v systemctl >/dev/null 2>&1; then
  fail "systemd is required."
fi

log "Installing for user ${RUN_USER} (${RUN_HOME})..."
log "Installing base packages..."
run_privileged apt-get update
run_privileged apt-get install -y ca-certificates curl git xvfb

if [ ! -x "${UV_BIN}" ]; then
  log "Installing uv for ${RUN_USER}..."
  as_run_user sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
fi

log "Using install directory ${INSTALL_DIR}..."

if [ -d "${INSTALL_DIR}/.git" ]; then
  log "Updating existing repository..."
  as_run_user git -C "${INSTALL_DIR}" remote set-url origin "${REPO_URL}"
  as_run_user git -C "${INSTALL_DIR}" pull --ff-only
elif [ -e "${INSTALL_DIR}" ]; then
  fail "${INSTALL_DIR} exists but is not a git repository."
else
  log "Cloning repository..."
  as_run_user git clone "${REPO_URL}" "${INSTALL_DIR}"
fi

cd "${INSTALL_DIR}"

log "Installing Python 3.14 with uv..."
as_run_user "${UV_BIN}" python install 3.14

log "Installing Python dependencies..."
as_run_user "${UV_BIN}" sync --locked

log "Installing Playwright Chromium..."
as_run_user "${UV_BIN}" run playwright install chromium

log "Installing Playwright Linux dependencies..."
run_privileged "${INSTALL_DIR}/.venv/bin/playwright" install-deps chromium

if [ ! -f "${INSTALL_DIR}/.env" ]; then
  log "Creating .env from .env.example..."
  as_run_user cp "${INSTALL_DIR}/.env.example" "${INSTALL_DIR}/.env"
fi

log "Installing systemd service..."
SERVICE_TMP="$(mktemp)"
cat > "${SERVICE_TMP}" <<EOF
[Unit]
Description=GMGN Forwarder Service
After=network.target

[Service]
Type=simple
User=${RUN_USER}
Group=${RUN_GROUP}
WorkingDirectory=${INSTALL_DIR}
Environment="PATH=${RUN_HOME}/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=${UV_BIN} run python main.py
Restart=always
RestartSec=10
RuntimeMaxSec=43200
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF
run_privileged install -m 0644 "${SERVICE_TMP}" "${SERVICE_TARGET}"
rm -f "${SERVICE_TMP}"
run_privileged systemctl daemon-reload
run_privileged systemctl enable "${SERVICE_NAME}"

if grep -q '123456:your_bot_token\|-1001234567890' "${INSTALL_DIR}/.env"; then
  cat <<EOF

${APP_NAME} is installed, but the service was not started.

Edit the environment file first:
  nano ${INSTALL_DIR}/.env

Then complete the first GMGN login in an interactive terminal:
  cd ${INSTALL_DIR}
  ${UV_BIN} run python main.py

After login state is saved, stop the foreground command with Ctrl+C and start the service:
  $(if [ "$(id -u)" -eq 0 ]; then printf 'systemctl'; else printf 'sudo systemctl'; fi) start ${SERVICE_NAME}
  $(if [ "$(id -u)" -eq 0 ]; then printf 'journalctl'; else printf 'sudo journalctl'; fi) -u ${APP_NAME} -f

EOF
  exit 0
fi

if [ ! -d "${INSTALL_DIR}/browser_data" ]; then
  cat <<EOF

${APP_NAME} is installed and enabled, but the service was not started.

Complete the first GMGN login in an interactive terminal:
  cd ${INSTALL_DIR}
  ${UV_BIN} run python main.py

After login state is saved, stop the foreground command with Ctrl+C and start the service:
  $(if [ "$(id -u)" -eq 0 ]; then printf 'systemctl'; else printf 'sudo systemctl'; fi) start ${SERVICE_NAME}
  $(if [ "$(id -u)" -eq 0 ]; then printf 'journalctl'; else printf 'sudo journalctl'; fi) -u ${APP_NAME} -f

EOF
  exit 0
fi

log "Starting service..."
run_privileged systemctl restart "${SERVICE_NAME}"
run_privileged systemctl status "${SERVICE_NAME}" --no-pager -l
