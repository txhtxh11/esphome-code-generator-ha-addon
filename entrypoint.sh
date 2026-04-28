#!/bin/bash
set -e

# ESPHome Code Generator - entrypoint wrapper
# Patches the ESPHome Dashboard to add the /generate route, then starts normally.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Patch web_server.py to add code generator routes
python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from code_generator import patch_make_app
patch_make_app()
print('[code-gen] ESPHome dashboard patched: /generate route added')
" 2>&1 | grep '\[code-gen\]'

# Start original ESPHome dashboard
exec esphome dashboard "$@"
