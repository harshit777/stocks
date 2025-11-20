#!/usr/bin/env python3
"""
Automated Zerodha Kite access token generation using Selenium.
This script automates the login process and generates a fresh access token.
"""
import os
import sys
import time
from urllib.parse import urlparse, parse_qs

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from kiteconnect import KiteConnect


def generate_token_with_selenium():
    """Generate access token using Selenium automation."""
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError as e:
        print(f"ERROR: Required package not installed: {e}")
        print("Run: pip install selenium webdriver-manager")
        return None
    
    # Get credentials from environment
    api_key = os.getenv('KITE_API_KEY')
    api_secret = os.getenv('KITE_API_SECRET')
    user_id = os.getenv('ZERODHA_USER_ID')
    password = os.getenv('ZERODHA_PASSWORD')
    pin = os.getenv('ZERODHA_PIN')
    
    if not all([api_key, api_secret, user_id, password, pin]):
        print("ERROR: Missing required environment variables")
        print("Required: KITE_API_KEY, KITE_API_SECRET, ZERODHA_USER_ID, ZERODHA_PASSWORD, ZERODHA_PIN")
        return None
    
    print("🔐 Starting automated token generation...")
    
    # Initialize KiteConnect
    kite = KiteConnect(api_key=api_key)
    login_url = kite.login_url()
    
    # Setup Chrome options for headless mode
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    
    driver = None
    try:
        # Initialize Chrome driver with auto-managed ChromeDriver
        print("🌐 Initializing Chrome browser...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        print(f"✅ Chrome initialized successfully")
        
        print(f"📍 Navigating to login URL...")
        driver.get(login_url)
        
        print("📝 Filling login form...")
        
        # Wait for and fill user ID
        user_id_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "userid"))
        )
        user_id_field.send_keys(user_id)
        
        # Fill password
        password_field = driver.find_element(By.ID, "password")
        password_field.send_keys(password)
        
        # Click login button
        login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        login_button.click()
        
        print("🔑 Entering PIN...")
        
        # Wait for PIN page and fill PIN
        pin_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "pin"))
        )
        pin_field.send_keys(pin)
        
        # Click continue button
        continue_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        continue_button.click()
        
        print("⏳ Waiting for redirect...")
        
        # Wait for redirect and capture request token
        WebDriverWait(driver, 10).until(
            lambda d: "request_token" in d.current_url or "status=error" in d.current_url
        )
        
        current_url = driver.current_url
        
        # Check for login errors
        if "status=error" in current_url:
            print("❌ Login failed. Check credentials.")
            return None
        
        # Parse request token from URL
        parsed_url = urlparse(current_url)
        query_params = parse_qs(parsed_url.query)
        
        if 'request_token' not in query_params:
            print("❌ No request token found in redirect URL")
            return None
        
        request_token = query_params['request_token'][0]
        print(f"✅ Request token obtained: {request_token[:10]}...")
        
        # Generate access token
        print("🔄 Generating access token...")
        data = kite.generate_session(request_token, api_secret=api_secret)
        access_token = data["access_token"]
        
        print(f"✅ Access token generated successfully!")
        print(f"Token: {access_token[:20]}...")
        
        return access_token
        
    except Exception as e:
        print(f"❌ Error during token generation: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
    
    finally:
        if driver:
            driver.quit()


def main():
    """Main function."""
    print("=" * 60)
    print("Automated Zerodha Kite Token Generator")
    print("=" * 60)
    print()
    
    access_token = generate_token_with_selenium()
    
    if access_token:
        print()
        print("=" * 60)
        print("✅ SUCCESS!")
        print("=" * 60)
        print(f"Access Token: {access_token}")
        print()
        
        # Output for GitHub Actions
        if os.getenv('GITHUB_ACTIONS'):
            # Write to GitHub Actions output
            with open(os.getenv('GITHUB_OUTPUT', '/dev/stdout'), 'a') as f:
                f.write(f"access_token={access_token}\n")
            print("✅ Token written to GitHub Actions output")
        
        return 0
    else:
        print()
        print("=" * 60)
        print("❌ FAILED")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
