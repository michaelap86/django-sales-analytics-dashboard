#!/usr/bin/env bash
# Install or update the app on PythonAnywhere. Run it from a Bash console:
#
#   bash <(curl -sL https://raw.githubusercontent.com/michaelap86/django-sales-analytics-dashboard/main/deploy/pythonanywhere.sh)
#
# First create the web app on the "Web" tab (Manual configuration, Python 3.12),
# then run this script, then set the virtualenv path it prints and press Reload.
set -euo pipefail

REPO_URL="https://github.com/michaelap86/django-sales-analytics-dashboard.git"
APP_DIR="$HOME/django-sales-analytics-dashboard"
DOMAIN="${USER}.pythonanywhere.com"
WSGI_FILE="/var/www/${USER}_pythonanywhere_com_wsgi.py"
PYTHON="${PYTHON:-python3.12}"

echo "==> Fetching code"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only
else
  git clone --depth 1 "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

echo "==> Installing packages"
[ -d .venv ] || "$PYTHON" -m venv .venv
.venv/bin/pip install --quiet --no-cache-dir --upgrade pip
.venv/bin/pip install --quiet --no-cache-dir -r requirements.txt

echo "==> Preparing database and static files"
export DJANGO_DEBUG=0 DJANGO_ALLOWED_HOSTS="$DOMAIN"
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput -v 0
.venv/bin/python manage.py seed_demo --if-empty

echo "==> Writing $WSGI_FILE"
cat > "$WSGI_FILE" <<EOF
import os
import sys

sys.path.insert(0, "$APP_DIR")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
os.environ["DJANGO_DEBUG"] = "0"
os.environ["DJANGO_ALLOWED_HOSTS"] = "$DOMAIN"
os.environ["DJANGO_CSRF_TRUSTED_ORIGINS"] = "https://$DOMAIN"

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
EOF

echo
echo "Done. On the Web tab:"
echo "  1. Virtualenv: $APP_DIR/.venv"
echo "  2. Force HTTPS: enabled"
echo "  3. Press Reload, then open https://$DOMAIN"
