#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 22.04/24.04 VM for HireLens (any size, x86 or ARM). Run ON the VM:
#   bash vm-setup.sh
# Safe to re-run. Adds swap, installs Docker, and opens ports 80/443 in Ubuntu's firewall.
# (Oracle's network security list must also allow 80/443; see DEPLOYMENT.md.)
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi

# 1. Swap: headroom for image builds, and essential on a 1 GB VM.
if ! swapon --show | grep -q /swapfile; then
  $SUDO fallocate -l 2G /swapfile
  $SUDO chmod 600 /swapfile
  $SUDO mkswap /swapfile >/dev/null
  $SUDO swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' | $SUDO tee -a /etc/fstab >/dev/null
  echo 'vm.swappiness=10' | $SUDO tee /etc/sysctl.d/99-hirelens-swap.conf >/dev/null
  $SUDO sysctl -q -p /etc/sysctl.d/99-hirelens-swap.conf
fi

# 2. Oracle's Ubuntu images ship iptables rules that reject everything except SSH. Open 80/443
#    in the running firewall and in the saved rules file. (Not via netfilter-persistent save:
#    with Docker running that would also persist Docker's own rules and break them on reboot.)
for port in 80 443; do
  rule=(-p tcp -m state --state NEW -m tcp --dport "$port" -j ACCEPT)
  if ! $SUDO iptables -C INPUT "${rule[@]}" 2>/dev/null; then
    reject_line="$($SUDO iptables -L INPUT --line-numbers -n | awk '$2 == "REJECT" { print $1; exit }')"
    if [ -n "$reject_line" ]; then
      $SUDO iptables -I INPUT "$reject_line" "${rule[@]}"
    else
      $SUDO iptables -A INPUT "${rule[@]}"
    fi
  fi
  saved=/etc/iptables/rules.v4
  if [ -f "$saved" ] && ! $SUDO grep -q -- "--dport $port -j ACCEPT" "$saved"; then
    $SUDO sed -i "0,/^-A INPUT -j REJECT/s//-A INPUT ${rule[*]}\n&/" "$saved"
  fi
done

# 3. Docker Engine and the Compose plugin, from Ubuntu's own packages.
if ! command -v docker >/dev/null; then
  $SUDO apt-get update -q
  $SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y -q docker.io docker-compose-v2 docker-buildx git
  $SUDO systemctl enable --now docker
fi
$SUDO usermod -aG docker "$(id -un)"

echo "Done. Log out and back in once so your user can run docker without sudo."
free -h | sed -n '1,3p'
docker --version 2>/dev/null || true
