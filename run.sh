#!/usr/bin/env bashio
set -e

CONFIG_PATH=/data/options.json

IOTICS_EMAIL=$(bashio::config 'iotics_email')
IOTICS_PASSWORD=$(bashio::config 'iotics_password')
IOTICS_APPID=$(bashio::config 'iotics_appid')

if [ -z "$IOTICS_EMAIL" ] || [ -z "$IOTICS_PASSWORD" ]; then
    bashio::log.error "Iotics email and password must be configured."
    exit 1
fi

bashio::log.info "Starting Iotics Smart Home Bridge..."
bashio::log.info "Email: ${IOTICS_EMAIL}"
bashio::log.info "App ID: ${IOTICS_APPID}"

python3 /bridge.py
