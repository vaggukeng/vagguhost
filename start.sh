#!/usr/bin/env bash
set -Eeuo pipefail

: "${BOT_TOKEN:?BOT_TOKEN is required}"
: "${FREE_TRIAL_PASSWORD:?FREE_TRIAL_PASSWORD is required}"

export PYTHONUNBUFFERED=1
exec python3 attached_assets/vagguhost_1785779614076.py