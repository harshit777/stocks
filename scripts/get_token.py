#!/usr/bin/env python3
"""
Helper script to generate Zerodha Kite access token.
"""
import sys
import os

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import os
from dotenv import load_dotenv
from src.kite_trader.trader import KiteTrader

# Load environment variables - override existing env vars
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path, override=True)

def main():
    print("=" * 60)
    print("Zerodha Kite Access Token Generator")
    print("=" * 60)
    print()
    
    # Initialize trader
    trader = KiteTrader()
    
    # Get login URL
    login_url = trader.get_login_url()
    
    if not login_url:
        print("ERROR: Could not generate login URL. Check your API key.")
        return
    
    print("Step 1: Visit this URL to login:")
    print()
    print(login_url)
    print()
    print("Step 2: After logging in, you'll be redirected to a URL.")
    print("        Copy the 'request_token' parameter from that URL.")
    print()
    
    # Get request token from user
    request_token = input("Paste the request_token here: ").strip()
    
    if not request_token:
        print("ERROR: No request token provided.")
        return
    
    print()
    print("Generating access token...")
    
    # Generate access token
    access_token = trader.set_access_token_from_request(request_token)
    
    if access_token:
        print()
        print("SUCCESS! Access token generated:")
        print(access_token)
        print()
        print("Step 3: Add this to your .env file:")
        print(f"KITE_ACCESS_TOKEN={access_token}")
        print()
        
        # Ask if user wants to update .env automatically
        update = input("Update .env file automatically? (y/n): ").strip().lower()
        
        if update == 'y':
            env_path = '.env'
            with open(env_path, 'r') as f:
                lines = f.readlines()
            
            # Update the access token line
            with open(env_path, 'w') as f:
                for line in lines:
                    if line.startswith('KITE_ACCESS_TOKEN='):
                        f.write(f'KITE_ACCESS_TOKEN={access_token}\n')
                    else:
                        f.write(line)
            
            print(f"✓ .env file updated successfully!")
            print()
            print("You can now run: source venv/bin/activate && python main.py")
        else:
            print("Please update your .env file manually.")
    else:
        print("ERROR: Failed to generate access token. Check your API secret and request token.")

if __name__ == "__main__":
    main()
