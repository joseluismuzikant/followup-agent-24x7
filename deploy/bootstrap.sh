#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 VM for inmo24x7 (Oracle Cloud ARM or any other).
# Run as root: sudo ./bootstrap.sh "<your ssh public key>". Safe to run again.
#
# Installs Docker and the compose plugin, creates the `deploy` user (SSH keys only), opens
# only 22/80/443, turns on unattended security upgrades, adds swap on small VMs, sets UTC, and
# installs the backup timer.
#
# Firewall: Oracle's Ubuntu images already filter with iptables (/etc/iptables/rules.v4, a
# final REJECT, iptables-persistent installed), and ufw cannot be installed next to it ("ufw
# Breaks iptables-persistent"). There, 80/443 are added to rules.v4 after the SSH rule. On any
# other Ubuntu (no rules.v4 with that SSH rule), UFW is used as before.
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
apt-get install -y -q ca-certificates curl gnupg unattended-upgrades

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
rules=/etc/iptables/rules.v4
ssh_rule='--dport 22 -j ACCEPT'
web_rules=(
	"-A INPUT -p tcp -m state --state NEW -m tcp --dport 80 -j ACCEPT"
	"-A INPUT -p tcp -m state --state NEW -m tcp --dport 443 -j ACCEPT"
	"-A INPUT -p udp -m state --state NEW -m udp --dport 443 -j ACCEPT"
)
if [[ -f "$rules" ]] && grep -q -- "$ssh_rule" "$rules"; then
	# Oracle's image. The saved rules: add the missing lines right after the SSH rule.
	missing=()
	for rule in "${web_rules[@]}"; do
		grep -qxF -- "$rule" "$rules" || missing+=("$rule")
	done
	if ((${#missing[@]})); then
		cp "$rules" "$rules.bak"
		SSH_RULE="$ssh_rule" ADD="$(printf '%s\n' "${missing[@]}")" awk '
			{ print }
			!done && index($0, ENVIRON["SSH_RULE"]) { print ENVIRON["ADD"]; done = 1 }
		' "$rules.bak" >"$rules"
	fi
	# The live rules, in the same place (after SSH, before the REJECT). Not iptables-restore:
	# that would drop Docker's chains. And never `netfilter-persistent save` once Docker runs:
	# it would write Docker's own chains into rules.v4.
	for rule in "${web_rules[@]}"; do
		read -ra spec <<<"${rule#-A INPUT }"
		if ! iptables -C INPUT "${spec[@]}" 2>/dev/null; then
			position="$(iptables -L INPUT --line-numbers -n |
				awk '/ACCEPT/ && /tcp dpt:22( |$)/ { print $1 + 1; exit }')"
			iptables -I INPUT "${position:-1}" "${spec[@]}"
		fi
	done
else
	# Any other Ubuntu: UFW.
	apt-get install -y -q ufw
	ufw default deny incoming
	ufw default allow outgoing
	ufw allow 22/tcp
	ufw allow 80/tcp
	ufw allow 443/tcp
	ufw allow 443/udp
	ufw --force enable
fi

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
install -d -m 750 -o deploy -g deploy "$app_dir" "$app_dir/releases"
install -m 640 -o deploy -g deploy "$here/.env.production.example" "$app_dir/"
# The same install the Deploy workflow runs on every deploy (install-files.sh), from a
# release folder named after this copy of deploy/.
release="$app_dir/releases/bootstrap"
rm -rf "$release"
cp -r "$here" "$release"
rm -rf "$release/rehearsal" "$release"/.env*
chown -R deploy:deploy "$release"
sudo -u deploy bash "$release/install-files.sh"
install -m 644 "$here/systemd/inmo24x7-backup.service" /etc/systemd/system/
install -m 644 "$here/systemd/inmo24x7-backup.timer" /etc/systemd/system/
systemctl daemon-reload
# Enabled once .env.production exists (docs/go-live.md); until then a run would fail.
if [[ -f "$app_dir/.env.production" ]]; then
	systemctl enable --now inmo24x7-backup.timer
fi

say "Done. Next: create $app_dir/.env.production (chmod 600) and run deploy.sh as deploy."
