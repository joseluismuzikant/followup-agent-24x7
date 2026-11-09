# Bootstrapping the VM

One Ubuntu 24.04 VM with Docker runs everything (api, worker, web, backoffice, Caddy). The
target is an Oracle Cloud Ampere (ARM) instance in São Paulo; any Linux VM works the same,
because CI builds amd64 and arm64 images.

## 1. Create the VM

- **Oracle:** Compute → Instances → Create. Image *Canonical Ubuntu 24.04*, shape
  *VM.Standard.A1.Flex* (2 OCPU / 12 GB is plenty; 1 OCPU / 6 GB works), region São Paulo,
  your SSH public key, a public IPv4.
  If the region is "out of capacity", retry later or use another provider: nothing here is
  Oracle-specific except the network rules below.
- **Open 80 and 443 in Oracle's network** (the VM firewall is not enough):
  Networking → Virtual cloud networks → your VCN → Security Lists → Default → Add ingress
  rules: source `0.0.0.0/0`, TCP, destination ports `80` and `443`. (Also UDP 443 for
  HTTP/3; optional.) SSH (22) is there by default.

## 2. Run the bootstrap

From your machine, copy the `deploy/` folder and run the script once as root:

```bash
scp -r deploy ubuntu@<vm-ip>:/tmp/inmo24x7-deploy
ssh ubuntu@<vm-ip> 'sudo /tmp/inmo24x7-deploy/bootstrap.sh "$(cat ~/.ssh/authorized_keys | head -n 1)"'
```

It is safe to run again. It:

- sets the timezone to UTC and installs Docker Engine + the compose plugin from Docker's
  repository;
- creates the `deploy` user (in the `docker` group) with your SSH key, and turns off password
  and root SSH logins;
- allows only 22, 80 and 443. On Oracle's Ubuntu images (iptables with
  `/etc/iptables/rules.v4` and a final REJECT; `ufw` cannot be installed there, it "Breaks
  iptables-persistent") it adds ACCEPT lines for tcp 80, tcp 443 and udp 443 to `rules.v4`
  right after the SSH rule and inserts the same live rules, without `netfilter-persistent
  save` (that would store Docker's own chains). On any other Ubuntu it uses UFW;
- turns on unattended security upgrades, and adds a 2 GB swap file when RAM < 8 GB;
- creates `/opt/inmo24x7` (owned by `deploy`) and installs the compose file, Caddyfile,
  scripts (`deploy.sh`, `dc.sh`, …), the backup image's sources and the logs stack's
  configuration with `install-files.sh` (the same install every deploy runs), and installs the
  backup timer (enabled once `.env.production` exists).

From now on, connect as `deploy`: `ssh deploy@<vm-ip>`.

## 3. Updating the deploy files later

Nothing to do: every deploy from GitHub uploads `deploy/` at the deployed commit and
installs it (`docs/go-live.md`, step 12). Only the systemd units need root: when they change,
the Deploy run shows the command to run on the VM. Running the bootstrap again also works; it
leaves `.env.production` and `state/` alone.
