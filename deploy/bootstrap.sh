#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 VM for inmo24x7 (Oracle Cloud ARM or any other).
# Run as root: sudo ./bootstrap.sh "<your ssh public key>". Safe to run again.
#
# Installs Docker and the compose plugin, creates the `deploy` user (SSH keys only), opens
# only 22/80/443 (UFW, plus Oracle's own iptables rules), turns on unattended security
# upgrades, adds swap on small VMs, sets UTC, and installs the backup timer.
set -euo pipefail

[[ $EUID -eq 0 ]] || {
	echo "Run as root (sudo)." >&2
	exit 1
}
public_key="${1:?usage: bootstrap.sh \"<ssh public key>\"}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
app_dir=/opt/inmo24x7

say() { printf '==> %s\n' "$*"; }

say "Timezone UTC and base packages"
timedatectl set-timezone UTC
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q ca-certificates curl gnupg ufw unattended-upgrades iptables-persistent

say "Docker Engine and the compose plugin (Docker's apt repository)"
if ! command -v docker >/dev/null; then
	install -m 0755 -d /etc/apt/keyrings
	curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
	chmod a+r /etc/apt/keyrings/docker.asc
	# shellcheck disable=SC1091
	codename="$(. /etc/os-release && echo "$VERSION_CODENAME")"
	echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc]" \
		"https://download.docker.com/linux/ubuntu $codename stable" \
		>/etc/apt/sources.list.d/docker.list
	apt-get update -q
	apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin \
		docker-compose-plugin
fi
systemctl enable --now docker

say "The deploy user (SSH keys only)"
id deploy >/dev/null 2>&1 || useradd --create-home --shell /bin/bash deploy
usermod -aG docker deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
touch /home/deploy/.ssh/authorized_keys
grep -qxF "$public_key" /home/deploy/.ssh/authorized_keys ||
	echo "$public_key" >>/home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
cat >/etc/ssh/sshd_config.d/60-inmo24x7.conf <<'SSHD'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
SSHD
systemctl reload ssh

say "Firewall: only 22, 80 and 443"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable
# Oracle's Ubuntu images ship iptables rules that REJECT everything but SSH, before UFW's
# chains: let HTTP and HTTPS in ahead of them, and keep it across reboots.
for rule in "-p tcp --dport 80" "-p tcp --dport 443" "-p udp --dport 443"; do
	# shellcheck disable=SC2086
	iptables -C INPUT $rule -j ACCEPT 2>/dev/null || iptables -I INPUT 1 $rule -j ACCEPT
done
netfilter-persistent save

say "Unattended security upgrades"
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'APT'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT
systemctl enable --now unattended-upgrades

say "Swap (2 GB) when the VM has less than 8 GB of RAM"
memory_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
if ((memory_kb < 8 * 1024 * 1024)) && ! swapon --show | grep -q /swapfile; then
	fallocate -l 2G /swapfile
	chmod 600 /swapfile
	mkswap /swapfile
	swapon /swapfile
	grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >>/etc/fstab
fi

say "The app directory and the backup timer"
install -d -m 750 -o deploy -g deploy "$app_dir"
for file in compose.prod.yml Caddyfile lib.sh deploy.sh restore.sh backup-now.sh \
	.env.production.example; do
	install -m 640 -o deploy -g deploy "$here/$file" "$app_dir/$file"
done
chmod 750 "$app_dir/deploy.sh" "$app_dir/restore.sh" "$app_dir/backup-now.sh"
cp -r "$here/backup" "$app_dir/" && chown -R deploy:deploy "$app_dir/backup"
install -m 644 "$here/systemd/inmo24x7-backup.service" /etc/systemd/system/
install -m 644 "$here/systemd/inmo24x7-backup.timer" /etc/systemd/system/
systemctl daemon-reload
# Enabled once .env.production exists (docs/go-live.md); until then a run would fail.
if [[ -f "$app_dir/.env.production" ]]; then
	systemctl enable --now inmo24x7-backup.timer
fi

say "Done. Next: create $app_dir/.env.production (chmod 600) and run deploy.sh as deploy."
