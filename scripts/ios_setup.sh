#!/bin/bash
# Quick setup script for iOS (iSH)

echo "Installing required packages for iSH..."
apk update
apk add coreutils github-cli

echo ""
echo "✅ Setup complete!"
echo ""
echo "Now run the token updater:"
echo "  ./scripts/mobile_update_token.sh"
