#!/usr/bin/env bash
# CareerBridge AI - READ-ONLY server check. Run on the EC2 instance:
#     bash server_audit.sh            (some checks need: sudo bash server_audit.sh)
#
# It only reads information and changes nothing. It never prints the contents
# of .env files or API keys - only whether the files exist and their permissions.
# Review the output before you share it, and remove any IP addresses or host names
# you do not want to share.

section() { printf '\n=== %s ===\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

section "Operating system"
( . /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" ) || uname -a
echo "Uptime: $(uptime -p 2>/dev/null || uptime)"
echo "Memory:"; free -h 2>/dev/null | head -2
echo "Disk (/):"; df -h / | tail -1

section "Listening ports (who is listening where)"
if have ss; then ss -tlnp 2>/dev/null | awk 'NR==1 || /:(22|80|443|5000|5055|8000)[[:space:]]/'; fi
echo "Expected: nginx on 0.0.0.0:80 and :443, gunicorn ONLY on 127.0.0.1:8000, nothing public on 5000/5055/8000."

section "Application processes"
ps -eo user,pid,etime,cmd 2>/dev/null | grep -E "[g]unicorn|[f]lask|[p]ython3? .*app\.py" || echo "No gunicorn/flask process found."

section "Python and the existing app"
for py in python3 python3.11 python3.12; do have "$py" && echo "$py: $($py --version 2>&1)"; done
echo "CareerBridge needs Python 3.10 or newer."
for d in "$HOME/careerbridge-ai" /home/*/careerbridge-ai /opt/careerbridge/app /var/www/careerbridge*; do
  [ -d "$d" ] || continue
  echo "App folder: $d ($(du -sh "$d" 2>/dev/null | cut -f1))"
  [ -d "$d/.git" ] && echo "  git: $(git -C "$d" log -1 --format='%h %ad %s' --date=short 2>/dev/null)  branch: $(git -C "$d" rev-parse --abbrev-ref HEAD 2>/dev/null)"
done

section "systemd services"
for unit in careerbridge nginx; do
  if systemctl list-unit-files "$unit.service" >/dev/null 2>&1 && systemctl list-unit-files "$unit.service" | grep -q "$unit"; then
    echo "$unit: enabled=$(systemctl is-enabled "$unit" 2>/dev/null) active=$(systemctl is-active "$unit" 2>/dev/null)"
  else
    echo "$unit: no systemd service installed"
  fi
done
echo "If careerbridge has no service, Gunicorn was probably started by hand and stops on reboot or logout."

section "Nginx"
if have nginx; then
  nginx -v 2>&1
  sudo -n nginx -t 2>&1 | tail -2 || echo "(run with sudo to test the configuration)"
  echo "Server blocks (listen / server_name / ssl_certificate):"
  sudo -n nginx -T 2>/dev/null | grep -E "^\s*(listen|server_name|ssl_certificate |return 301|proxy_pass|proxy_read_timeout|client_max_body_size)" | sed 's/^\s*/  /' | sort | uniq -c
else
  echo "Nginx is not installed."
fi

section "TLS certificates (Let's Encrypt)"
if have certbot; then
  certbot --version 2>&1
  sudo -n certbot certificates 2>/dev/null | grep -E "Certificate Name|Domains|Expiry Date" || echo "(run with sudo to list certificates)"
  systemctl list-timers 2>/dev/null | grep -i certbot || echo "No certbot timer found (check cron: sudo crontab -l)."
else
  echo "Certbot is not installed - HTTPS is probably not set up yet."
fi
ls -d /etc/letsencrypt/live/*/ 2>/dev/null | sed 's#^#Certificate folder: #' || true

section "Secrets (permissions only, contents are never shown)"
for f in /etc/careerbridge/careerbridge.env "$HOME/careerbridge-ai/.env" /opt/careerbridge/app/.env ./.env; do
  [ -e "$f" ] && stat -c '%A %U:%G %n' "$f"
done
echo "Expected: -rw------- or -rw-r----- (600/640), owned by the app user. Never world-readable."
if [ -d "$HOME/careerbridge-ai/.git" ]; then
  ( cd "$HOME/careerbridge-ai" && git check-ignore -q .env && echo ".env is ignored by git: yes" || echo "WARNING: .env is not ignored by git" )
fi

section "Host firewall"
if have firewall-cmd; then sudo -n firewall-cmd --list-all 2>/dev/null || echo "firewalld installed (run with sudo)";
elif have ufw; then sudo -n ufw status verbose 2>/dev/null || echo "ufw installed (run with sudo)";
else echo "No host firewall tool found. On EC2 the security group is the main firewall - check it in the AWS console."; fi

section "Automatic security updates"
if have dnf; then echo "Pending security updates:"; dnf -q updateinfo list --security 2>/dev/null | wc -l; fi
if have apt; then apt list --upgradable 2>/dev/null | grep -ci security | sed 's/^/Pending security upgrades: /'; fi

section "Local HTTP checks"
have curl && {
  echo "Gunicorn (127.0.0.1:8000/health): $(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)"
  echo "Flask dev port (127.0.0.1:5055/health): $(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:5055/health) (000 = not running, which is good in production)"
}
echo; echo "Done. Nothing was changed."
