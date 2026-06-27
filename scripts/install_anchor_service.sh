#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: install_anchor_service.sh [local|server] [--public-url URL] [--desktop-url URL]

Installs a user-level ANCHOR systemd service template, writes mode-specific env files,
and optionally refreshes the desktop launcher for the selected URL.

Defaults:
  local  -> 127.0.0.1:8765
  server -> 0.0.0.0:8767
EOF
}

mode="local"
public_url=""
desktop_url=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    local|server)
      mode="$1"
      shift
      ;;
    --public-url)
      public_url="${2:-}"
      shift 2
      ;;
    --desktop-url)
      desktop_url="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
 done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
home_dir="$HOME"
config_dir="$home_dir/.config/anchor"
unit_dir="$home_dir/.config/systemd/user"
desktop_dir="$home_dir/.local/share/applications"
mkdir -p "$config_dir" "$unit_dir" "$desktop_dir"

case "$mode" in
  local)
    host="127.0.0.1"
    port="8765"
    public_url="${public_url:-http://127.0.0.1:8765/anchor}"
    desktop_url="${desktop_url:-$public_url}"
    ;;
  server)
    host="0.0.0.0"
    port="8767"
    if [[ -z "$public_url" ]]; then
      echo "server mode requires --public-url http://<host>:8767/anchor" >&2
      exit 2
    fi
    desktop_url="${desktop_url:-$public_url}"
    ;;
  *)
    echo "Unknown mode: $mode" >&2
    exit 2
    ;;
esac

cat > "$unit_dir/anchor-web@.service" <<EOF
[Unit]
Description=ANCHOR dashboard web service (%i)
After=network-online.target

[Service]
Type=simple
EnvironmentFile=%h/.config/anchor/anchor-web-%i.env
ExecStart=$repo_root/scripts/run_anchor_web.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

cat > "$config_dir/anchor-web-local.env" <<EOF
# Local ANCHOR web service environment
ANCHOR_PROJECT_ROOT=$repo_root
ANCHOR_WEB_HOST=127.0.0.1
ANCHOR_PORT=8765
ANCHOR_PUBLIC_URL=http://127.0.0.1:8765/anchor
EOF

cat > "$config_dir/anchor-web-server.env" <<EOF
# Server ANCHOR web service environment
# Update ANCHOR_PUBLIC_URL to the droplet IP or hostname you want operators to use.
ANCHOR_PROJECT_ROOT=$repo_root
ANCHOR_WEB_HOST=0.0.0.0
ANCHOR_PORT=8767
ANCHOR_PUBLIC_URL=$public_url
EOF

cat > "$desktop_dir/anchor.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=ANCHOR
GenericName=Security Research OS
Comment=Open the ANCHOR dashboard
Exec=/usr/bin/env ANCHOR_DASHBOARD_URL="$desktop_url" "$repo_root"/scripts/open_anchor_dashboard.sh
Icon=web-browser
Terminal=false
Categories=Utility;
StartupNotify=true
EOF

if command -v desktop-file-validate >/dev/null 2>&1; then
  desktop-file-validate "$desktop_dir/anchor.desktop"
fi

systemctl --user daemon-reload
if systemctl --user is-active --quiet anchor-web.service; then
  systemctl --user disable --now anchor-web.service
fi
systemctl --user enable --now "anchor-web@${mode}.service"

echo "ANCHOR installer complete."
echo "Mode: $mode"
echo "Service: anchor-web@${mode}.service"
echo "Desktop launcher: $desktop_dir/anchor.desktop"
echo "Dashboard URL: $desktop_url"
