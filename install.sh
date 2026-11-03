#!/usr/bin/env bash
set -euo pipefail

APP_NAME="jbl-quantum910-tray"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SHARE_DIR="${HOME}/.local/share/${APP_NAME}"
BIN_DIR="${HOME}/.local/bin"
SYSTEMD_DIR="${HOME}/.config/systemd/user"

WRAPPER_PATH="${BIN_DIR}/${APP_NAME}"
APP_PATH="${SHARE_DIR}/jbl_quantum910_tray.py"
SERVICE_SRC="${ROOT_DIR}/systemd/jbl-quantum910-tray.service"
SERVICE_DST="${SYSTEMD_DIR}/jbl-quantum910-tray.service"

echo "==> Instalando ${APP_NAME} (user-level)"

if [[ ! -x /usr/bin/python3 ]]; then
  echo "ERRO: /usr/bin/python3 não encontrado. Instale o Python do sistema." >&2
  exit 1
fi

if ! /usr/bin/python3 -c "import usb.core" 2>/dev/null; then
  echo "AVISO: pyusb não encontrado no Python do sistema (sudo apt install -y python3-usb)." >&2
  echo "       O app usará apenas hidraw." >&2
fi

mkdir -p "${SHARE_DIR}" "${BIN_DIR}" "${SYSTEMD_DIR}"

echo "==> Copiando app para ${APP_PATH}"
cp -f "${ROOT_DIR}/jbl_quantum910_tray.py" "${APP_PATH}"
chmod +x "${APP_PATH}"

echo "==> Criando wrapper em ${WRAPPER_PATH}"
cat > "${WRAPPER_PATH}" <<'EOF'
#!/usr/bin/env sh
exec /usr/bin/python3 "$HOME/.local/share/jbl-quantum910-tray/jbl_quantum910_tray.py" "$@"
EOF
chmod +x "${WRAPPER_PATH}"

echo "==> Instalando service systemd --user"
cp -f "${SERVICE_SRC}" "${SERVICE_DST}"

echo "==> Recarregando systemd (user) e habilitando"
systemctl --user daemon-reload
systemctl --user enable jbl-quantum910-tray.service
systemctl --user restart jbl-quantum910-tray.service

echo
echo "OK. Instalado e iniciado."
echo
echo "Comandos úteis:"
echo "  - status:  systemctl --user status jbl-quantum910-tray.service"
echo "  - logs:    journalctl --user -u jbl-quantum910-tray.service -f"
echo "  - parar:   systemctl --user stop jbl-quantum910-tray.service"
echo
echo "Se o tray não aparecer, instale as dependências do AppIndicator:"
echo "  Debian/Ubuntu: sudo apt install -y python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1"

