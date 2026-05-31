# ---------------------------------------------------------------
# Iotics Switches Addon for Home Assistant — Dockerfile
# 
# This file tells Docker how to build the container that runs the
# addon. It starts from the official Home Assistant base image,
# installs Python libraries, and copies our bridge code inside.
# ---------------------------------------------------------------

# ARG BUILD_FROM is a special Home Assistant variable. When the
# supervisor builds this addon, it replaces BUILD_FROM with the
# correct base image for your architecture (e.g., aarch64 for
# Raspberry Pi, amd64 for Intel/AMD systems).
ARG BUILD_FROM

# Use the HA-provided base image as our starting point.
FROM $BUILD_FROM

# Install Python 3 and pip inside the container. The `apk add`
# command is Alpine Linux's package manager (the base image is
# Alpine-based). `--no-cache` keeps the image smaller by not
# storing package cache files.
RUN apk add --no-cache python3 py3-pip

# Install the two Python libraries we need:
#   paho-mqtt    — for connecting to AWS IoT via MQTT WebSockets
#   websockets   — for listening to Home Assistant events in real time
RUN pip3 install --no-cache-dir \
    paho-mqtt \
    websockets

# Copy our files from the build folder into the container's root (/).
# run.sh    — the startup script that reads config and launches bridge.py
# bridge.py — the main program that does everything
COPY run.sh /
COPY bridge.py /

# Make sure run.sh can be executed (chmod a+x = add execute permission
# for all users: owner, group, and others).
RUN chmod a+x /run.sh

# Tell Docker what command to run when the container starts.
# The supervisor will run this whenever the addon starts or restarts.
CMD [ "/run.sh" ]
