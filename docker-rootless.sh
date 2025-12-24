#!/bin/bash
set -euo pipefail

########################################
# CONFIG
########################################
SSH_PORT=2222
ADMIN_USER="admin"
DOCKER_USER="dockersvc"
TIMEZONE="UTC"

########################################
# BASE SYSTEM
########################################
timedatectl set-timezone "$TIMEZONE"
apt update && apt upgrade -y

apt install -y \
  ca-certificates \
  curl \
  gnupg \
  uidmap \
  dbus-user-session \
  slirp4netns \
  fuse-overlayfs \
  iptables \
  ufw \
  fail2ban \
  unattended-upgrades \
  auditd

########################################
# USERS
########################################
id "$ADMIN_USER" &>/dev/null || adduser --disabled-password --gecos "" "$ADMIN_USER"
usermod -aG sudo "$ADMIN_USER"

id "$DOCKER_USER" &>/dev/null || adduser --disabled-password --gecos "" "$DOCKER_USER"

########################################
# SSH HARDENING
########################################
sed -i \
  -e "s/^#*Port .*/Port $SSH_PORT/" \
  -e "s/^#*PermitRootLogin .*/PermitRootLogin no/" \
  -e "s/^#*PasswordAuthentication .*/PasswordAuthentication no/" \
  /etc/ssh/sshd_config

echo "AllowUsers $ADMIN_USER" >> /etc/ssh/sshd_config
systemctl restart ssh

########################################
# FIREWALL
########################################
ufw default deny incoming
ufw default allow outgoing
ufw allow "$SSH_PORT/tcp"
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

########################################
# FAIL2BAN
########################################
cat >/etc/fail2ban/jail.local <<EOF
[sshd]
enabled = true
port = $SSH_PORT
bantime = 1h
maxretry = 5
EOF

systemctl enable fail2ban
systemctl restart fail2ban

########################################
# DOCKER ROOTLESS INSTALL
########################################
echo "🐳 Installing Docker Rootless..."

curl -fsSL https://get.docker.com | sh

loginctl enable-linger "$DOCKER_USER"

sudo -u "$DOCKER_USER" bash <<EOF
export XDG_RUNTIME_DIR=/run/user/$(id -u $DOCKER_USER)
dockerd-rootless-setuptool.sh install
systemctl --user enable docker
systemctl --user start docker
EOF

########################################
# PORT REDIRECT (80/443 → ROOTLESS)
########################################
echo "🔁 Redirecting ports 80/443 → 8080/8443"

iptables -t nat -A PREROUTING -p tcp --dport 80  -j REDIRECT --to-port 8080
iptables -t nat -A PREROUTING -p tcp --dport 443 -j REDIRECT --to-port 8443

########################################
# PERSIST IPTABLES
########################################
apt install -y iptables-persistent
netfilter-persistent save

########################################
# AUDIT
########################################
systemctl enable auditd
systemctl start auditd

########################################
# FINAL
########################################
echo
echo "✅ ZERO-TRUST DOCKER ROOTLESS READY"
echo "SSH user       : $ADMIN_USER"
echo "Docker user    : $DOCKER_USER"
echo "SSH port       : $SSH_PORT"
echo
echo "⚠️ Docker commands:"
echo "sudo -u $DOCKER_USER docker ps"
