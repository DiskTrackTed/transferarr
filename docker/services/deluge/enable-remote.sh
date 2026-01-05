#!/bin/bash
# Enable remote RPC connections in Deluge
# This script is run as a custom init script for the linuxserver deluge container

CONFIG_FILE="/config/core.conf"

# Wait for Deluge to create the initial config
echo "Waiting for Deluge config to be created..."
while [ ! -f "$CONFIG_FILE" ]; do
    sleep 1
done

# Wait a bit more for Deluge to finish writing
sleep 2

# Check if allow_remote is already enabled
if grep -q '"allow_remote": true' "$CONFIG_FILE"; then
    echo "Remote connections already enabled"
    exit 0
fi

# Stop deluged temporarily to modify config safely
echo "Stopping deluged to modify config..."
pkill -f deluged || true
sleep 2

# Enable allow_remote using sed (handles JSON format)
echo "Enabling allow_remote in $CONFIG_FILE..."
sed -i 's/"allow_remote": false/"allow_remote": true/g' "$CONFIG_FILE"

# Verify the change
if grep -q '"allow_remote": true' "$CONFIG_FILE"; then
    echo "Successfully enabled remote connections"
else
    echo "WARNING: Failed to enable remote connections"
fi

# Deluge will be restarted by the container's supervisor
echo "Config updated. Deluge will restart automatically."
