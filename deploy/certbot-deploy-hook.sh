#!/bin/sh
# Reloads Nginx after Certbot renews a certificate, so the new certificate is used.
# Install: sudo install -m 755 deploy/certbot-deploy-hook.sh /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
set -e
nginx -t -q && systemctl reload nginx
