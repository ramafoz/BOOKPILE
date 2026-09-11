#!/usr/bin/env bash

set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root (for example: sudo bash $0)." >&2
  exit 1
fi

if [[ ! -r /etc/os-release ]]; then
  echo "Cannot identify the operating system." >&2
  exit 1
fi

# shellcheck disable=SC1091
. /etc/os-release
if [[ "${ID:-}" != "ubuntu" || "${VERSION_CODENAME:-}" != "noble" ]]; then
  echo "This installer is restricted to Ubuntu 24.04 (noble)." >&2
  exit 1
fi

admin_user="${BOOKPILE_ADMIN_USER:-${SUDO_USER:-bookpileadmin}}"
if ! id "${admin_user}" >/dev/null 2>&1; then
  echo "Administrator account ${admin_user} does not exist." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y ca-certificates curl git gnupg unattended-upgrades

install -m 0755 -d /etc/apt/keyrings
curl --fail --silent --show-error --location \
  https://download.docker.com/linux/ubuntu/gpg \
  --output /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

architecture="$(dpkg --print-architecture)"
cat > /etc/apt/sources.list.d/docker.list <<EOF
deb [arch=${architecture} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable
EOF

apt-get update
apt-get install -y \
  containerd.io \
  docker-buildx-plugin \
  docker-ce \
  docker-ce-cli \
  docker-compose-plugin

systemctl enable --now docker
systemctl enable --now unattended-upgrades
usermod -aG docker "${admin_user}"

docker version --format 'Docker Engine {{.Server.Version}}'
docker compose version

echo
echo "Host packages are ready. Sign out and reconnect before using Docker as ${admin_user}."
