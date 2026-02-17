#!/usr/bin/env bash
# Smoke test: --list shows decrypted previews for auto-encrypted clips
# Uses TEECLIP_HOME to isolate from user's real history
set -e

TEECLIP_HOME=$(mktemp -d)
export TEECLIP_HOME

cat > "$TEECLIP_HOME/config.toml" << 'EOF'
[security]
encryption = "aes256"
auth_method = "os"
EOF

echo "--- Saving 3 clips with auto-encryption ---"
echo "my secret password" | python -m teeclip --no-clipboard
echo "API_KEY=sk-abc123def456" | python -m teeclip --no-clipboard
echo "just a normal note" | python -m teeclip --no-clipboard

echo ""
echo "--- List (should show decrypted previews + [encrypted] marker) ---"
python -m teeclip --list

echo ""
echo "--- Get 1 (should decrypt transparently) ---"
python -m teeclip --get 1 --no-clipboard

echo ""
echo "--- Files created ---"
ls -la "$TEECLIP_HOME/"

# Cleanup
rm -rf "$TEECLIP_HOME"
echo ""
echo "--- PASS ---"
