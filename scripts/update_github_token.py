#!/usr/bin/env python3
"""
Generate Zerodha token locally (with manual login) and update GitHub secrets.

This script:
1. Opens browser for you to login to Zerodha manually
2. Captures the access token
3. Updates the GitHub repository secret automatically

Usage:
    python3 scripts/update_github_token.py --repo USERNAME/REPO_NAME --token GITHUB_TOKEN
"""
import os
import sys
import argparse
import subprocess
from urllib.parse import urlparse, parse_qs

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
from kiteconnect import KiteConnect

# Load environment
load_dotenv()


def generate_token_manually():
    """Generate access token with manual browser login."""
    api_key = os.getenv('KITE_API_KEY')
    api_secret = os.getenv('KITE_API_SECRET')
    
    if not api_key or not api_secret:
        print("❌ ERROR: KITE_API_KEY and KITE_API_SECRET must be set in .env")
        return None
    
    kite = KiteConnect(api_key=api_key)
    login_url = kite.login_url()
    
    print("=" * 70)
    print("🔐 Zerodha Token Generator for GitHub Actions")
    print("=" * 70)
    print()
    print("Step 1: Login to Zerodha")
    print("-" * 70)
    print("Opening browser... Please login manually")
    print()
    
    # Open browser
    try:
        if sys.platform == 'darwin':  # macOS
            subprocess.run(['open', login_url])
        elif sys.platform == 'win32':  # Windows
            subprocess.run(['start', login_url], shell=True)
        else:  # Linux
            subprocess.run(['xdg-open', login_url])
    except:
        print(f"Please open this URL manually:\n{login_url}\n")
    
    print("After logging in, you'll be redirected to a URL.")
    print("Copy the ENTIRE redirect URL and paste it here.")
    print()
    redirect_url = input("Paste the redirect URL: ").strip()
    
    if not redirect_url:
        print("❌ No URL provided")
        return None
    
    # Parse request token
    try:
        parsed = urlparse(redirect_url)
        params = parse_qs(parsed.query)
        
        if 'request_token' not in params:
            print("❌ No request_token found in URL")
            return None
        
        request_token = params['request_token'][0]
        print(f"\n✅ Request token: {request_token[:10]}...")
        
        # Generate access token
        print("🔄 Generating access token...")
        data = kite.generate_session(request_token, api_secret=api_secret)
        access_token = data["access_token"]
        
        print(f"✅ Access token generated successfully!")
        return access_token
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def update_github_secret(repo, github_token, secret_name, secret_value):
    """Update GitHub repository secret using GitHub CLI."""
    try:
        # Check if gh CLI is installed
        result = subprocess.run(['gh', '--version'], capture_output=True, text=True)
        if result.returncode != 0:
            print("❌ GitHub CLI (gh) is not installed")
            print("Install it from: https://cli.github.com/")
            return False
        
        print(f"\n🔄 Updating GitHub secret: {secret_name}")
        
        # Update secret using gh CLI
        cmd = [
            'gh', 'secret', 'set', secret_name,
            '--repo', repo,
            '--body', secret_value
        ]
        
        env = os.environ.copy()
        env['GITHUB_TOKEN'] = github_token
        
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ GitHub secret updated successfully!")
            return True
        else:
            print(f"❌ Failed to update secret: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error updating GitHub secret: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Generate token and update GitHub secrets')
    parser.add_argument('--repo', help='GitHub repository (USERNAME/REPO)', 
                       default=os.getenv('GITHUB_REPOSITORY'))
    parser.add_argument('--token', help='GitHub personal access token',
                       default=os.getenv('GITHUB_TOKEN'))
    
    args = parser.parse_args()
    
    # Generate token manually
    access_token = generate_token_manually()
    
    if not access_token:
        print("\n❌ Failed to generate access token")
        return 1
    
    print()
    print("=" * 70)
    print("✅ Access Token Generated")
    print("=" * 70)
    print(f"\nToken: {access_token}")
    print()
    
    # Ask if user wants to update GitHub
    if args.repo and args.token:
        update = input(f"Update GitHub secret for {args.repo}? (y/n): ").strip().lower()
        
        if update == 'y':
            success = update_github_secret(
                args.repo,
                args.token,
                'KITE_ACCESS_TOKEN',
                access_token
            )
            
            if success:
                print()
                print("=" * 70)
                print("🎉 All Done!")
                print("=" * 70)
                print("Your GitHub Actions workflow will now use the new token.")
                print("The token is valid until end of trading day.")
                return 0
    else:
        print("To update GitHub secrets automatically, run:")
        print(f"  python3 {__file__} --repo USERNAME/REPO --token YOUR_GITHUB_TOKEN")
        print()
        print("Or update manually:")
        print(f"  1. Go to: https://github.com/YOUR_USERNAME/YOUR_REPO/settings/secrets/actions")
        print(f"  2. Update KITE_ACCESS_TOKEN with: {access_token}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
