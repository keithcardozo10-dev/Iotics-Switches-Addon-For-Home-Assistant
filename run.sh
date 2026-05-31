#!/usr/bin/env bashio
# ---------------------------------------------------------------
# Iotics Switches Addon for Home Assistant — Startup Script
#
# This is the first thing that runs when the addon container starts.
# It reads the user's configuration (email, password, appid) from
# /data/options.json (written by the HA supervisor), validates it,
# and then launches bridge.py which does all the actual work.
# ---------------------------------------------------------------

# Exit immediately if any command fails. This prevents the addon
# from running with partial or missing configuration.
set -e

# The path where HA supervisor stores the addon's configuration.
# When the user fills in the fields (email, password, appid) in
# the HA addon UI, the supervisor writes them to this file.
CONFIG_PATH=/data/options.json

# Read configuration values using bashio (the HA helper tool).
# bashio::config reads from /data/options.json and returns the
# value for the given key. If the key is missing, it returns empty.
IOTICS_EMAIL=$(bashio::config 'iotics_email')
IOTICS_PASSWORD=$(bashio::config 'iotics_password')
IOTICS_APPID=$(bashio::config 'iotics_appid')

# If email or password are empty, the user hasn't configured the
# addon yet. Log an error and stop — there's no point continuing
# without credentials to log into the Iotics cloud.
if [ -z "$IOTICS_EMAIL" ] || [ -z "$IOTICS_PASSWORD" ]; then
    bashio::log.error "Iotics email and password must be configured."
    exit 1
fi

# Log the startup info so the user can see what's happening.
# bashio::log.info prints to the addon's log tab in the HA UI.
bashio::log.info "Starting Iotics Switches Addon..."
bashio::log.info "Email: ${IOTICS_EMAIL}"
bashio::log.info "App ID: ${IOTICS_APPID}"

# Launch the main bridge program. This runs forever (it has its own
# loops for MQTT, HA events, etc.) and only exits on error.
python3 /bridge.py
