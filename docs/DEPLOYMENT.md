# Deployment guide: AWS EC2, Nginx, Gunicorn and HTTPS

This guide explains how to check the existing CareerBridge AI server safely and how to deploy version 2 with HTTPS.

> **Nothing in this guide has been run against the live server yet.** Parts 1 and 6 are read-only. Parts 4 and 5 change the server and should only be carried out after the read-only check and an explicit decision.

```
Browser ──HTTPS 443──▶ Nginx (TLS, HTTP→HTTPS redirect, rate limit) ──HTTP 127.0.0.1:8000──▶ Gunicorn ──▶ Flask app ──HTTPS──▶ Gemini API
        ──HTTP 80───▶ Nginx: only Let's Encrypt validation + 301 redirect (no app content)
```

| File | Installed as | Purpose |
|---|---|---|
| `deploy/gunicorn.conf.py` | used from the app folder | Gunicorn on `127.0.0.1:8000`, 120 s worker timeout, threads |
| `deploy/careerbridge.service` | `/etc/systemd/system/careerbridge.service` | Starts the app on boot, restarts it on failure, sandboxed |
| `deploy/nginx/careerbridge.conf` | `/etc/nginx/conf.d/careerbridge.conf` | Ports 80 and 443, redirect, TLS, HSTS, upload limits, rate limit |
| `deploy/nginx/careerbridge-proxy.conf` | `/etc/nginx/careerbridge-proxy.conf` | Shared reverse-proxy settings and timeouts |
| `deploy/nginx/careerbridge-bootstrap.conf` | temporary | Answers only the Let's Encrypt challenge before the first certificate exists |
| `deploy/certbot-deploy-hook.sh` | `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh` | Reloads Nginx after a certificate renewal |
| `deploy/certbot-renew.service` / `.timer` | `/etc/systemd/system/` | Automatic renewal when Certbot is installed with pip |
| `deploy/server_audit.sh` | run on the server | **Read-only** check of the current server |
| `deploy/verify_deployment.sh` | run on your computer | **Read-only** check of the public site (redirect, TLS, headers, ports) |

---

## Part 1 – Check the existing deployment (read-only)

### 1a. In the AWS console (no tools needed)

1. **EC2 → Instances** in the region where the server was created (for example **Europe (Stockholm) eu-north-1**). Note the instance state (*running* / *stopped*), instance type, public IPv4 address and whether it has an **Elastic IP**.
2. **Instance → Security → Security groups → Inbound rules.** Compare with the target rules in Part 2.
3. **Route 53 → Registered domains / Hosted zones.** Shows whether you already own a domain in this AWS account.
4. **Billing → Bills / Cost Explorer.** A running instance, its disk (EBS) and its public IPv4 address all cost money, even when nobody uses the site.

### 1b. With the AWS CLI (optional, read-only commands)

These commands only *describe* resources. Use a profile with read-only permissions if you can.

```bash
aws sts get-caller-identity
aws ec2 describe-instances --region <region> \
  --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,Type:InstanceType,PublicIp:PublicIpAddress,Name:Tags[?Key==`Name`]|[0].Value,Groups:SecurityGroups[].GroupId}' \
  --output table
aws ec2 describe-security-groups --region <region> --group-ids <sg-id> \
  --query 'SecurityGroups[].IpPermissions[].{From:FromPort,To:ToPort,Proto:IpProtocol,IPv4:IpRanges[].CidrIp,IPv6:Ipv6Ranges[].CidrIpv6}' \
  --output table
aws ec2 describe-addresses --region <region>
aws route53 list-hosted-zones
aws route53domains list-domains --region us-east-1
```

### 1c. On the server (read-only)

```bash
ssh ec2-user@<public-ip>                 # Amazon Linux uses ec2-user, Ubuntu uses ubuntu
curl -O https://raw.githubusercontent.com/nedababaki-pixel/careerbridge-ai/<branch>/deploy/server_audit.sh
less server_audit.sh                      # read it first: it only reads information
sudo bash server_audit.sh > audit.txt
```

The script shows the OS, listening ports, Gunicorn/Nginx/systemd status, certificates, firewall and **only the permissions** of `.env` files (never their contents). Remove IP addresses and host names before sharing `audit.txt`.

---

## Part 2 – Target security group (firewall)

| Direction | Port | Source | Why |
|---|---|---|---|
| Inbound | 22 (SSH) | **My IP only** (`x.x.x.x/32`) | Administration. Better: EC2 Instance Connect or Systems Manager Session Manager and no open port 22 |
| Inbound | 80 (HTTP) | `0.0.0.0/0`, `::/0` | Let's Encrypt validation and redirect to HTTPS only |
| Inbound | 443 (HTTPS) | `0.0.0.0/0`, `::/0` | The application |
| Inbound | 5000, 5055, 8000 | **none** | Flask/Gunicorn must never be public |
| Outbound | 443 | `0.0.0.0/0` | Gemini API, package updates, Let's Encrypt |

Port 80 stays open on purpose: it never serves CV data, it only redirects to HTTPS (tested: a `POST /api/analyze` over HTTP gets `301` and never reaches the app).

---

## Part 3 – HTTPS: choosing a host name

A browser-trusted certificate needs a name that Let's Encrypt can validate.

| Option | Cost | Trusted by browsers | Notes |
|---|---|---|---|
| **A. Own domain** (e.g. from a registrar or Route 53) | Domain fee per year (+ $0.50/month if you use a Route 53 hosted zone) | Yes | Most professional for a portfolio. Standard 90-day Let's Encrypt certificate, automatic renewal |
| **B. Free subdomain** from a dynamic-DNS service (e.g. DuckDNS) | Free | Yes | Works with the same Nginx config and Certbot. Depends on a third-party DNS service |
| **C. Let's Encrypt certificate for the IP address** | Free | Yes | Generally available since January 2026. Certificates last only about 6 days (`shortlived` profile), need Certbot ≥ 5.4 with `--webroot`, and the Nginx plugin cannot install them. Needs a fixed IP (Elastic IP). Visitors see an IP address instead of a name |
| D. Self-signed certificate | Free | **No** (browser warning) | Only for private testing, not for a public portfolio |

Every option also needs a stable public IPv4 address. AWS charges for public IPv4 addresses (about $0.005 per hour per address – check current pricing). An Elastic IP keeps the same address after a stop/start; an auto-assigned address changes.

**Recommendation:** option A, or option B if you do not want to pay for a domain. Both use the configuration in this folder unchanged.

### Option B step by step (DuckDNS)

1. Allocate an **Elastic IP** and associate it with the instance (no extra cost while it is attached; the old auto-assigned address is released).
2. Sign in at duckdns.org, create a subdomain (for example `careerbridge-<name>.duckdns.org`) and set its IPv4 to the Elastic IP. Keep the DuckDNS token private – it is not needed on the server, because the IP no longer changes.
3. Check from your own computer: `nslookup careerbridge-<name>.duckdns.org` must show the Elastic IP.
4. Continue with Part 5, using that name as `<your-domain>`.

---

## Part 4 – Backup before any change (only after approval)

Version 1 keeps running until version 2 has passed its checks, so the site is never left half-changed.

| Layer | What is saved | How | Cost |
|---|---|---|---|
| Whole disk | Complete EBS volume of the instance | **EC2 → Volumes → Create snapshot** (name: `careerbridge-before-v2-<date>`). Wait until the state is *completed* | about $0.05 per GB-month (8 GB ≈ $0.40/month); delete the snapshot when version 2 has run without problems for a few weeks |
| App files | Old app folder, Nginx configuration, service files | The commands below, on the server | free (stays on the disk) |
| Network | Security group rules, public IP, DNS | Screenshot or copy of the inbound rules and the current public IP | free |

```bash
# On the server, before changing anything (read the output, nothing is deleted)
B=/root/careerbridge-backup-$(date +%Y%m%d-%H%M)
sudo mkdir -p "$B"
sudo tar -czf "$B/nginx.tgz" /etc/nginx
sudo tar -czf "$B/systemd.tgz" /etc/systemd/system/*.service 2>/dev/null
sudo tar -czf "$B/app-v1.tgz" --exclude='.venv' --exclude='venv' <old-app-folder>    # from server_audit.sh
sudo crontab -l > "$B/root-crontab.txt" 2>/dev/null; crontab -l > "$B/user-crontab.txt" 2>/dev/null
ps -eo user,pid,cmd | grep -E "[g]unicorn|[p]ython" > "$B/processes.txt"
sudo ls -la "$B"
```

The old `.env` stays where it is and is never copied into the backup archive's name, Git or chat.

### Rollback plan

| Problem after the change | Back to a working state |
|---|---|
| Version 2 does not start (`systemctl status careerbridge` fails) | `sudo systemctl disable --now careerbridge`, then start version 1 the same way it ran before (command saved in `processes.txt`) |
| Nginx configuration error | `sudo tar -xzf $B/nginx.tgz -C /` then `sudo nginx -t && sudo systemctl reload nginx` |
| A later app update breaks something | `sudo -u careerbridge git -C /opt/careerbridge/app checkout <previous-commit>` and `sudo systemctl restart careerbridge` |
| Certificate or DNS problem | Nginx bootstrap config (HTTP only) keeps the site reachable while the certificate is fixed |
| Server unusable | Create a volume from the snapshot and attach it, or launch a new instance from the snapshot |
| Elastic IP no longer wanted | Disassociate **and release** it, otherwise AWS charges for an unattached address |

---

## Part 5 – Deploy version 2 (changes the server – only after approval)

Commands are for **Amazon Linux 2023** (`dnf`). On Ubuntu use `apt` and `python3`.
CareerBridge needs **Python 3.10 or newer**; Amazon Linux 2023's default `python3` is 3.9, so install `python3.11`.

```bash
# 1. Packages and a dedicated, unprivileged app user
sudo dnf install -y nginx git python3.11
sudo useradd --system --home /opt/careerbridge --shell /sbin/nologin careerbridge

# 2. Code and virtual environment
sudo mkdir -p /opt/careerbridge && sudo chown careerbridge:careerbridge /opt/careerbridge
sudo -u careerbridge git clone https://github.com/nedababaki-pixel/careerbridge-ai.git /opt/careerbridge/app
sudo -u careerbridge python3.11 -m venv /opt/careerbridge/venv
sudo -u careerbridge /opt/careerbridge/venv/bin/pip install -r /opt/careerbridge/app/requirements.txt

# 3. Secrets outside the code folder (type the key on the server, never in Git or chat)
sudo mkdir -p /etc/careerbridge
sudo install -m 640 -o root -g careerbridge /opt/careerbridge/app/.env.example /etc/careerbridge/careerbridge.env
sudo nano /etc/careerbridge/careerbridge.env      # set GEMINI_API_KEY=...

# 4. App service. Version 1 on CloudCare-Web already runs as a systemd unit with the SAME name
#    (careerbridge.service, user ec2-user, /home/ec2-user/careerbridge-ai). The backup in Part 4 saves that
#    unit file; copying the new unit replaces it, and the restart below stops version 1 and starts version 2.
#    Rollback: restore the old unit from systemd.tgz, then daemon-reload and restart careerbridge.
#    If version 1 still listens on 127.0.0.1:8000 (see server_audit.sh), stop it first
#    with the command that started it (saved in processes.txt) - otherwise the ports collide.
sudo cp /opt/careerbridge/app/deploy/careerbridge.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable careerbridge && sudo systemctl restart careerbridge
curl -s http://127.0.0.1:8000/health            # {"status":"ok"}

# 5. First certificate (option A/B). Point the domain's A record to the server first.
sudo mkdir -p /var/www/letsencrypt
sudo cp /opt/careerbridge/app/deploy/nginx/careerbridge-bootstrap.conf /etc/nginx/conf.d/careerbridge.conf
sudo nginx -t && sudo systemctl enable --now nginx
sudo python3.11 -m venv /opt/certbot && sudo /opt/certbot/bin/pip install certbot
sudo /opt/certbot/bin/certbot certonly --webroot -w /var/www/letsencrypt -d <your-domain> --staging   # test first
sudo /opt/certbot/bin/certbot certonly --webroot -w /var/www/letsencrypt -d <your-domain>             # real certificate

# 6. Final Nginx config (replace careerbridge.example.com with your domain first)
sudo cp /opt/careerbridge/app/deploy/nginx/careerbridge-proxy.conf /etc/nginx/careerbridge-proxy.conf
sudo sed "s/careerbridge.example.com/<your-domain>/g" /opt/careerbridge/app/deploy/nginx/careerbridge.conf \
  | sudo tee /etc/nginx/conf.d/careerbridge.conf >/dev/null
sudo nginx -t && sudo systemctl reload nginx

# 7. Automatic renewal
sudo install -m 755 /opt/careerbridge/app/deploy/certbot-deploy-hook.sh /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
sudo cp /opt/careerbridge/app/deploy/certbot-renew.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now certbot-renew.timer
sudo /opt/certbot/bin/certbot renew --dry-run
```

For **option C (IP certificate)**: use `certbot certonly --preferred-profile shortlived --webroot -w /var/www/letsencrypt --ip-address <elastic-ip>` (Certbot ≥ 5.4), set `server_name` to the IP in `careerbridge.conf` and point the certificate paths to `/etc/letsencrypt/live/<ip>/`. The renewal timer and deploy hook above are essential because the certificate expires after about 6 days.

### Updating the app later

```bash
cd /opt/careerbridge/app && sudo -u careerbridge git pull
sudo -u careerbridge /opt/careerbridge/venv/bin/pip install -r requirements.txt
sudo systemctl restart careerbridge
```

---

## Part 6 – Verify (read-only, from your own computer)

```bash
bash deploy/verify_deployment.sh <your-domain>
```

It checks: HTTP → HTTPS redirect (also for the API), trusted certificate, `/health`, security headers, TLS 1.2/1.3 only, days until the certificate expires, and that ports 8000/5000/5055 are closed. It exits with an error if any check fails.

---

## What was tested before deployment

The configuration was run end-to-end on a local replica (Ubuntu 24.04, Nginx 1.24, Gunicorn 26) with a test certificate and a simulated Gemini API:

| Check | Result |
|---|---|
| `nginx -t` on the final config | syntax ok |
| `http://<domain>/page?x=1` | `301` to `https://<domain>/page?x=1` |
| `POST http://<domain>/api/analyze` with CV text | `301`; the app never received the request |
| `/.well-known/acme-challenge/` on port 80 | served from the webroot (needed by Let's Encrypt) |
| Unknown host name / raw IP on 80 and 443 | connection closed / TLS handshake rejected |
| HTTPS | `200` over HTTP/2, TLS 1.3 works, TLS 1.1 refused |
| Security headers over HTTPS | CSP, X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy, HSTS (sent once) |
| 4 MB PDF upload through Nginx | `200`, no request body written to Nginx temp files |
| 7 MB upload | `413` from Nginx |
| AI answer that takes **40 s** | `200` (with the original Gunicorn defaults this failed after 30 s) |
| Burst of API requests | `429` after the allowed burst |
| Spoofed `X-Forwarded-For` header | ignored; the app sees the real client IP |
| `systemd-analyze verify` on the unit files | no errors apart from the not-yet-installed program paths |

A real Let's Encrypt certificate, the AWS security group and the live EC2 instance have **not** been tested, because they require access to your AWS account and a domain.
