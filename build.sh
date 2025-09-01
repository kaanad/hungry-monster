#!/usr/bin/env bash
# exit on error
set -o errexit

# Update package lists and install system dependencies for Pillow
apt-get update
apt-get install -y libjpeg-dev zlib1g-dev
