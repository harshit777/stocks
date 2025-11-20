#!/usr/bin/env python3
"""
Quick token generator for Zerodha Kite
"""
import os
import sys

# Set environment variables
os.environ['KITE_API_KEY'] = 'on15r1ghrzpnjs0k'
os.environ['KITE_API_SECRET'] = 'tx2u7zxaq5zvu8zhrjzsexk58fwpdglu'

# Add project to path
sys.path.insert(0, '/Users/harshit/dev/go/src/github.com/stocks')

from src.kite_trader.trader import KiteTrader

def main():
    print("=" * 70)
    print("Zerodha Kite Token Generator")
    print("=" * 70)
    print()
    
    # Initialize trader
    trader = KiteTrader()
    
    # Get login URL
    login_url = trader.get_login_url()
    print("Step 1: Visit this URL in your browser:")
    print()
    print(login_url)
    print()
    print("Step 2: Login with your Zerodha credentials")
    print("Step 3: After login, copy the 'request_token' from the redirect URL")
    print()
    print("-" * 70)
    print()
    
    # Get request token from user
    request_token = input("Paste the request_token here: ").strip()
    
    if not request_token:
        print("ERROR: No request token provided")
        return
    
    print()
    print("Generating access token...")
    
    # Generate access token
    access_token = trader.set_access_token_from_request(request_token)
    
    if access_token:
        print()
        print("✓ SUCCESS! Access token generated:")
        print(access_token)
        print()
        
        # Update .env file
        print("Updating .env file...")
        env_path = '/Users/harshit/dev/go/src/github.com/stocks/.env'
        
        try:
            with open(env_path, 'r') as f:
                lines = f.readlines()
            
            with open(env_path, 'w') as f:
                for line in lines:
                    if line.startswith('KITE_ACCESS_TOKEN'):
                        f.write(f"KITE_ACCESS_TOKEN='{access_token}'\n")
                    else:
                        f.write(line)
            
            print("✓ .env file updated successfully!")
            print()
            print("=" * 70)
            print("You can now start paper trading with:")
            print("  python3 scripts/paper_trade.py")
            print("=" * 70)
        except Exception as e:
            print(f"ERROR updating .env: {e}")
            print()
            print("Please manually update your .env file with:")
            print(f"KITE_ACCESS_TOKEN='{access_token}'")
    else:
        print()
        print("ERROR: Failed to generate access token")
        print("Please check your API secret and request token")

if __name__ == "__main__":
    main()
