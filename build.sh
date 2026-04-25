#!/usr/bin/env bash
set -e

# Install Tesseract OCR (required for receipt photo parsing)
apt-get update -qq && apt-get install -y --no-install-recommends tesseract-ocr

pip install -r requirements.txt
