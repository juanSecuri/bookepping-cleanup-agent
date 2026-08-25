#!/usr/bin/env bash
# Build LedgerAI on Render: Python deps + frontend SPA.
set -euo pipefail

echo "==> Installing Python package"
python -m pip install --upgrade pip
pip install -e .

echo "==> Installing Node.js (nvm)"
export NVM_DIR="${HOME}/.nvm"
if [[ ! -s "${NVM_DIR}/nvm.sh" ]]; then
  curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
fi
# shellcheck disable=SC1091
. "${NVM_DIR}/nvm.sh"
nvm install 20
nvm use 20

echo "==> Building frontend"
cd frontend
npm ci
npm run build
cd ..

echo "==> Build complete (frontend/dist ready)"
