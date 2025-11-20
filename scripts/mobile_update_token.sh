#!/bin/bash
# Mobile Token Updater for Zerodha + GitHub
# Can be run on iOS (via a-Shell/iSH) or Android (via Termux)

set -e

# Colors for output (if terminal supports it)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
GITHUB_REPO="${GITHUB_REPO:-}"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
KITE_API_KEY="${KITE_API_KEY:-}"
KITE_API_SECRET="${KITE_API_SECRET:-}"

print_header() {
    echo ""
    echo "================================"
    echo "$1"
    echo "================================"
    echo ""
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Check if we're on a mobile device
check_environment() {
    if [ -n "$TERMUX_VERSION" ]; then
        print_info "Running on Android (Termux)"
        MOBILE_ENV="termux"
    elif [ "$(uname)" = "Darwin" ] && [ -n "$IPHONE_OS" ]; then
        print_info "Running on iOS"
        MOBILE_ENV="ios"
    else
        print_info "Running on desktop/server"
        MOBILE_ENV="desktop"
    fi
}

# Install dependencies if needed
check_dependencies() {
    print_header "Checking Dependencies"
    
    # Check for curl
    if ! command -v curl &> /dev/null; then
        print_error "curl is not installed"
        if [ "$MOBILE_ENV" = "termux" ]; then
            print_info "Run: pkg install curl"
        elif [ "$MOBILE_ENV" = "ios" ]; then
            print_info "Run: apk add curl"
        fi
        exit 1
    fi
    
    # Check for sha256sum or shasum
    if ! command -v sha256sum &> /dev/null && ! command -v shasum &> /dev/null; then
        print_error "sha256sum not found"
        if [ "$MOBILE_ENV" = "ios" ]; then
            print_info "Run: apk add coreutils"
        elif [ "$MOBILE_ENV" = "termux" ]; then
            print_info "Run: pkg install coreutils"
        fi
        exit 1
    fi
    
    # Check for gh CLI
    if ! command -v gh &> /dev/null; then
        print_warning "GitHub CLI (gh) not found"
        print_info "Install from: https://cli.github.com/"
        if [ "$MOBILE_ENV" = "termux" ]; then
            print_info "On Termux: pkg install gh"
        elif [ "$MOBILE_ENV" = "ios" ]; then
            print_info "On iSH: apk add github-cli"
        fi
        USE_MANUAL_UPDATE=true
    else
        print_success "GitHub CLI found"
        USE_MANUAL_UPDATE=false
    fi
}

# Load configuration from .env or prompt user
load_config() {
    print_header "Configuration"
    
    # Try to load from .env file
    if [ -f ".env" ]; then
        export $(grep -v '^#' .env | xargs)
        print_success "Loaded config from .env"
    fi
    
    # Prompt for missing values
    if [ -z "$KITE_API_KEY" ]; then
        echo -n "Enter your Kite API Key: "
        read KITE_API_KEY
    fi
    
    if [ -z "$KITE_API_SECRET" ]; then
        echo -n "Enter your Kite API Secret: "
        read -s KITE_API_SECRET
        echo ""
    fi
    
    if [ -z "$GITHUB_REPO" ]; then
        echo -n "Enter your GitHub repo (username/repo): "
        read GITHUB_REPO
    fi
    
    if [ -z "$GITHUB_TOKEN" ] && [ "$USE_MANUAL_UPDATE" != true ]; then
        echo -n "Enter your GitHub Personal Access Token: "
        read -s GITHUB_TOKEN
        echo ""
    fi
    
    print_success "Configuration loaded"
}

# Generate Zerodha login URL
generate_login_url() {
    print_header "Step 1: Login to Zerodha"
    
    LOGIN_URL="https://kite.zerodha.com/connect/login?api_key=${KITE_API_KEY}"
    
    print_info "Open this URL in your browser:"
    echo ""
    echo "$LOGIN_URL"
    echo ""
    
    # Try to open URL automatically
    if [ "$MOBILE_ENV" = "termux" ]; then
        termux-open-url "$LOGIN_URL" 2>/dev/null || true
    elif [ "$MOBILE_ENV" = "ios" ]; then
        open "$LOGIN_URL" 2>/dev/null || true
    elif command -v xdg-open &> /dev/null; then
        xdg-open "$LOGIN_URL" 2>/dev/null || true
    fi
}

# Get request token from user
get_request_token() {
    print_header "Step 2: Get Request Token"
    
    print_info "After logging in, you'll be redirected to a URL"
    print_info "The URL will look like:"
    echo "  http://127.0.0.1/?request_token=XXXXXX&action=login&status=success"
    echo ""
    echo -n "Paste the FULL redirect URL here: "
    read REDIRECT_URL
    
    # Extract request token from URL (BusyBox compatible)
    REQUEST_TOKEN=$(echo "$REDIRECT_URL" | sed -n 's/.*request_token=\([^&]*\).*/\1/p')
    
    if [ -z "$REQUEST_TOKEN" ]; then
        print_error "Could not extract request_token from URL"
        print_info "Please paste just the request_token value:"
        echo -n "Request Token: "
        read REQUEST_TOKEN
    fi
    
    if [ -z "$REQUEST_TOKEN" ]; then
        print_error "No request token provided"
        exit 1
    fi
    
    print_success "Request token captured: ${REQUEST_TOKEN:0:10}..."
    
    # Save request token to config file
    if [ -f ".mobile_token_config" ]; then
        # Update existing config file
        if grep -q "^KITE_REQUEST_TOKEN=" .mobile_token_config; then
            sed -i.bak "s|^KITE_REQUEST_TOKEN=.*|KITE_REQUEST_TOKEN=\"$REQUEST_TOKEN\"|" .mobile_token_config
            rm -f .mobile_token_config.bak
        else
            echo "KITE_REQUEST_TOKEN=\"$REQUEST_TOKEN\"" >> .mobile_token_config
        fi
    else
        # Create new config file with just the request token
        cat > .mobile_token_config << EOF
# Mobile Token Updater Config
# Generated on $(date)
KITE_REQUEST_TOKEN="$REQUEST_TOKEN"
EOF
        chmod 600 .mobile_token_config
    fi
    print_success "Request token saved to .mobile_token_config"
}

# Generate access token
generate_access_token() {
    print_header "Step 3: Generate Access Token"
    
    print_info "Calling Zerodha API..."
    
    # Calculate checksum (try sha256sum first, fallback to shasum)
    if command -v sha256sum &> /dev/null; then
        CHECKSUM=$(echo -n "${KITE_API_KEY}${REQUEST_TOKEN}${KITE_API_SECRET}" | sha256sum | cut -d' ' -f1)
    elif command -v shasum &> /dev/null; then
        CHECKSUM=$(echo -n "${KITE_API_KEY}${REQUEST_TOKEN}${KITE_API_SECRET}" | shasum -a 256 | cut -d' ' -f1)
    else
        print_error "Neither sha256sum nor shasum found"
        print_info "On iSH, install: apk add coreutils"
        exit 1
    fi
    
    # Make API call
    RESPONSE=$(curl -s -X POST "https://api.kite.trade/session/token" \
        -d "api_key=${KITE_API_KEY}" \
        -d "request_token=${REQUEST_TOKEN}" \
        -d "checksum=${CHECKSUM}")
    
    # Parse access token from JSON response (BusyBox compatible)
    ACCESS_TOKEN=$(echo "$RESPONSE" | sed -n 's/.*"access_token":"\([^"]*\).*/\1/p')
    
    if [ -z "$ACCESS_TOKEN" ]; then
        print_error "Failed to generate access token"
        print_error "Response: $RESPONSE"
        exit 1
    fi
    
    print_success "Access token generated!"
    echo ""
    echo "Token: $ACCESS_TOKEN"
    echo ""
    
    # Save access token to config file
    if [ -f ".mobile_token_config" ]; then
        # Update existing config file
        if grep -q "^KITE_ACCESS_TOKEN=" .mobile_token_config; then
            sed -i.bak "s|^KITE_ACCESS_TOKEN=.*|KITE_ACCESS_TOKEN=\"$ACCESS_TOKEN\"|" .mobile_token_config
            rm -f .mobile_token_config.bak
        else
            echo "KITE_ACCESS_TOKEN=\"$ACCESS_TOKEN\"" >> .mobile_token_config
        fi
    else
        # Create new config file with just the access token
        cat > .mobile_token_config << EOF
# Mobile Token Updater Config
# Generated on $(date)
KITE_ACCESS_TOKEN="$ACCESS_TOKEN"
EOF
        chmod 600 .mobile_token_config
    fi
    print_success "Access token saved to .mobile_token_config as KITE_ACCESS_TOKEN"
}

# Update GitHub secret
update_github_secret() {
    print_header "Step 4: Update GitHub Secret"
    
    if [ "$USE_MANUAL_UPDATE" = true ]; then
        print_warning "GitHub CLI not available - manual update required"
        echo ""
        print_info "Go to: https://github.com/${GITHUB_REPO}/settings/secrets/actions"
        print_info "Update KITE_ACCESS_TOKEN with:"
        echo ""
        echo "  $ACCESS_TOKEN"
        echo ""
        print_info "Press Enter when done..."
        read
    else
        print_info "Updating GitHub secret via API..."
        
        # Verify GitHub token is available
        if [ -z "$GITHUB_TOKEN" ]; then
            print_error "GitHub token not found"
            print_info "Set GITHUB_TOKEN in .mobile_token_config or as environment variable"
            exit 1
        fi
        
        # Get repository public key for encryption
        print_info "Fetching repository public key..."
        REPO_KEY_RESPONSE=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
            -H "Accept: application/vnd.github.v3+json" \
            "https://api.github.com/repos/${GITHUB_REPO}/actions/secrets/public-key")
        
        # Extract key_id and key from JSON (handle multiline response)
        KEY_ID=$(echo "$REPO_KEY_RESPONSE" | tr -d '\n' | sed -n 's/.*"key_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
        PUBLIC_KEY=$(echo "$REPO_KEY_RESPONSE" | tr -d '\n' | sed -n 's/.*"key"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
        
        print_info "Key ID: ${KEY_ID:0:20}..."
        print_info "Public Key: ${PUBLIC_KEY:0:20}..."
        
        if [ -z "$KEY_ID" ] || [ -z "$PUBLIC_KEY" ]; then
            print_error "Could not extract public key from API response"
            print_error "Response: $REPO_KEY_RESPONSE"
            exit 1
        fi
        
        print_success "Public key fetched successfully"
        print_info "Encrypting secret..."
        
        # Check for python3
        if ! command -v python3 &> /dev/null; then
            print_error "Python3 is required for secret encryption"
            if [ "$MOBILE_ENV" = "termux" ]; then
                print_info "Run: pkg install python"
            elif [ "$MOBILE_ENV" = "ios" ]; then
                print_info "Run: apk add python3"
            else
                print_info "Install Python3 from: https://www.python.org/downloads/"
            fi
            exit 1
        fi
        
        # Try using Python with PyNaCl
        ENCRYPT_OUTPUT=$(python3 -c "
import sys
import base64
try:
    from nacl import encoding, public
    public_key = public.PublicKey('$PUBLIC_KEY', encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt('$ACCESS_TOKEN'.encode('utf-8'))
    print(base64.b64encode(encrypted).decode('utf-8'))
except ImportError as e:
    print('ERROR:PyNaCl not installed', file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f'ERROR:{str(e)}', file=sys.stderr)
    sys.exit(1)
" 2>&1)
        
        ENCRYPT_EXIT_CODE=$?
        
        if [ $ENCRYPT_EXIT_CODE -ne 0 ]; then
            print_error "Encryption process failed with exit code $ENCRYPT_EXIT_CODE"
            print_error "Output: $ENCRYPT_OUTPUT"
        fi
        
        ENCRYPTED_VALUE="$ENCRYPT_OUTPUT"
        
        # Check if encryption succeeded
        if echo "$ENCRYPTED_VALUE" | grep -q "ERROR:"; then
            ERROR_MSG=$(echo "$ENCRYPTED_VALUE" | grep "ERROR:" | sed 's/.*ERROR://')
            print_error "Encryption failed: $ERROR_MSG"
            
            if echo "$ERROR_MSG" | grep -q "PyNaCl"; then
                print_info "Install PyNaCl:"
                if [ "$MOBILE_ENV" = "termux" ]; then
                    print_info "  pkg install python-cryptography"
                    print_info "  pip install PyNaCl"
                elif [ "$MOBILE_ENV" = "ios" ]; then
                    print_info "  pip3 install PyNaCl"
                else
                    print_info "  pip3 install PyNaCl"
                fi
            fi
            exit 1
        fi
        
        if [ -z "$ENCRYPTED_VALUE" ]; then
            print_error "Failed to encrypt secret"
            exit 1
        fi
        
        print_success "Secret encrypted successfully"
        print_info "Updating GitHub secret..."
        
        # Update secret via API
        UPDATE_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X PUT \
            -H "Authorization: token $GITHUB_TOKEN" \
            -H "Accept: application/vnd.github.v3+json" \
            "https://api.github.com/repos/${GITHUB_REPO}/actions/secrets/KITE_ACCESS_TOKEN" \
            -d "{\"encrypted_value\":\"$ENCRYPTED_VALUE\",\"key_id\":\"$KEY_ID\"}")
        
        HTTP_CODE=$(echo "$UPDATE_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
        
        if [ "$HTTP_CODE" = "201" ] || [ "$HTTP_CODE" = "204" ]; then
            print_success "GitHub secret updated successfully!"
        else
            print_error "Failed to update GitHub secret"
            print_error "HTTP Code: $HTTP_CODE"
            print_error "Response: $(echo "$UPDATE_RESPONSE" | grep -v "HTTP_CODE:")"
            exit 1
        fi
    fi
}

# Save config for next time
save_config() {
    print_header "Save Configuration?"
    
    echo -n "Save API keys for next time? (y/n): "
    read SAVE_CHOICE
    
    if [ "$SAVE_CHOICE" = "y" ] || [ "$SAVE_CHOICE" = "Y" ]; then
        cat > .mobile_token_config << EOF
# Mobile Token Updater Config
# Generated on $(date)
KITE_API_KEY="$KITE_API_KEY"
KITE_API_SECRET="$KITE_API_SECRET"
GITHUB_REPO="$GITHUB_REPO"
GITHUB_TOKEN="$GITHUB_TOKEN"
EOF
        chmod 600 .mobile_token_config
        print_success "Config saved to .mobile_token_config"
    fi
}

# Main execution
main() {
    print_header "🔐 Zerodha Token Updater (Mobile)"
    
    # Load saved config if exists
    if [ -f ".mobile_token_config" ]; then
        source .mobile_token_config
        print_success "Loaded saved configuration"
    fi
    
    check_environment
    check_dependencies
    load_config
    generate_login_url
    get_request_token
    generate_access_token
    update_github_secret
    
    if [ ! -f ".mobile_token_config" ]; then
        save_config
    fi
    
    print_header "✅ All Done!"
    print_success "Token is valid until end of trading day"
    print_info "Run this script again tomorrow morning before 9:15 AM"
}

# Run main function
main
