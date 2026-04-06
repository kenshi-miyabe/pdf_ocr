#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INSTALL_DIR="${1:-/usr/local/bin}"
TARGET_PATH="${INSTALL_DIR}/pdf_ocr"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv が見つかりません。先に uv をインストールしてください。" >&2
  exit 1
fi

mkdir -p "${INSTALL_DIR}"

cat > "${TARGET_PATH}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec uv run --project "${REPO_ROOT}" python "${REPO_ROOT}/pdf_ocr.py" "\$@"
EOF

chmod 755 "${TARGET_PATH}"

echo "Installed: ${TARGET_PATH}"
echo "Usage: pdf_ocr /path/to/pdf_directory"
