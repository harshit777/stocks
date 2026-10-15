#!/usr/bin/env python3
"""
kite_auth.py — Automatically fetch a fresh Kite access token.

Flow:
  1. POST credentials to Zerodha login  → request_id
  2. POST 2FA code (TOTP from authenticator app)  → request_token
  3. kite.generate_session()  → access_token
  4. Write KITE_ACCESS_TOKEN back into .env

2FA options (set ZERODHA_TOTP_SECRET or ZERODHA_PIN in .env):
  - TOTP (Google Authenticator / Zerodha app):
      Add ZERODHA_TOTP_SECRET=<base32 secret from Zerodha's TOTP setup page>
      Zerodha shows this when you enable TOTP — it's the secret behind the QR code.
  - SMS fallback: not supported here (requires manual intervention).

Usage:
  python3 kite_auth.py          # updates .env in place
  python3 kite_auth.py --print  # print token only
"""
import re
import sys
import warnings
import urllib.parse
from pathlib import Path
warnings.filterwarnings('ignore', category=Warning, module='urllib3')

ROOT     = Path(__file__).parent
ENV_FILE = ROOT / '.env'


def _load_env() -> dict:
    """Last occurrence of a key wins — matches shell/dotenv behaviour."""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if v and v != 'your_totp_base32_secret' and not v.startswith('your_'):
                    env[k] = v   # skip placeholder values
    return env


def _write_token(token: str):
    text = ENV_FILE.read_text() if ENV_FILE.exists() else ''
    if 'KITE_ACCESS_TOKEN=' in text:
        text = re.sub(r'^KITE_ACCESS_TOKEN=.*$', f'KITE_ACCESS_TOKEN={token}',
                      text, flags=re.MULTILINE)
    else:
        text = text.rstrip('\n') + f'\nKITE_ACCESS_TOKEN={token}\n'
    ENV_FILE.write_text(text)
    print(f'✓ .env updated — KITE_ACCESS_TOKEN={token[:8]}...')


def get_access_token(api_key: str, api_secret: str,
                     user_id: str, password: str,
                     totp_secret: str) -> str:
    import requests
    import pyotp
    from kiteconnect import KiteConnect

    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0'})

    # ── Step 1: Password login ─────────────────────────────────────────────
    print('→ Logging in...')
    r = session.post('https://kite.zerodha.com/api/login',
                     data={'user_id': user_id, 'password': password}, timeout=10)
    r.raise_for_status()
    body = r.json()
    if body.get('status') != 'success':
        raise RuntimeError(f"Login failed: {body.get('message', body)}")
    request_id = body['data']['request_id']
    print(f'  ✓ request_id={request_id[:8]}...')

    # ── Step 2: TOTP 2FA ───────────────────────────────────────────────────
    totp_code = pyotp.TOTP(totp_secret).now()
    print(f'→ Submitting TOTP {totp_code}...')
    r = session.post('https://kite.zerodha.com/api/twofa',
                     data={'user_id': user_id, 'request_id': request_id,
                           'twofa_value': totp_code, 'twofa_type': 'totp'},
                     timeout=10, allow_redirects=False)

    # After successful 2FA, Zerodha redirects to the app's redirect_url with request_token
    # Follow redirects manually to capture the Location header
    request_token = None

    # Check the initial response for redirect
    location = r.headers.get('Location', '')
    m = re.search(r'request_token=([^&]+)', location)
    if m:
        request_token = urllib.parse.unquote(m.group(1))

    # If no redirect yet, follow the connect/login redirect flow
    if not request_token and r.status_code in (200, 302):
        # Trigger the connect login flow — stop before the external redirect_url
        connect_url = (f'https://kite.zerodha.com/connect/login'
                       f'?api_key={api_key}&v=3')
        r2 = session.get(connect_url, timeout=10, allow_redirects=False)
        # Walk redirects manually, stop as soon as we have request_token
        while True:
            loc = r2.headers.get('Location', '')
            m = re.search(r'request_token=([^&]+)', loc)
            if m:
                request_token = urllib.parse.unquote(m.group(1))
                break
            if r2.status_code not in (301, 302, 303, 307, 308) or not loc:
                break
            # Only follow redirects that stay on kite.zerodha.com
            if 'kite.zerodha.com' not in loc and loc.startswith('http'):
                # External redirect — request_token is in this URL
                m = re.search(r'request_token=([^&]+)', loc)
                if m:
                    request_token = urllib.parse.unquote(m.group(1))
                break
            r2 = session.get(loc, timeout=10, allow_redirects=False)

    if not request_token:
        raise RuntimeError(
            f"Could not extract request_token.\n"
            f"2FA status={r.status_code} body={r.text[:200]}\n"
            "Verify ZERODHA_TOTP_SECRET is correct."
        )
    print(f'  ✓ request_token={request_token[:8]}...')

    # ── Step 3: Exchange for access_token ──────────────────────────────────
    print('→ Generating access token...')
    kite = KiteConnect(api_key=api_key)
    data = kite.generate_session(request_token, api_secret=api_secret)
    access_token = data['access_token']
    print(f'  ✓ access_token={access_token[:8]}...')
    return access_token


def main():
    print_only = '--print' in sys.argv
    env = _load_env()

    missing = [k for k in ('KITE_API_KEY', 'KITE_API_SECRET',
                            'ZERODHA_USER_ID', 'ZERODHA_PASSWORD')
               if not env.get(k)]
    if missing:
        print(f'✗ Missing in .env: {", ".join(missing)}')
        sys.exit(1)

    totp_secret = env.get('ZERODHA_TOTP_SECRET', '').strip()
    if not totp_secret:
        print(
            '\n✗ ZERODHA_TOTP_SECRET not set in .env\n'
            '\nHow to get it:\n'
            '  1. Open Zerodha Kite → My Account → Security → Enable TOTP\n'
            '  2. When the QR code appears, click "Can\'t scan? Use secret key"\n'
            '  3. Copy that base32 secret key\n'
            '  4. Add to .env:  ZERODHA_TOTP_SECRET=<paste here>\n'
            '  5. Re-run: python3 kite_auth.py\n'
        )
        sys.exit(1)

    token = get_access_token(
        api_key     = env['KITE_API_KEY'],
        api_secret  = env['KITE_API_SECRET'],
        user_id     = env['ZERODHA_USER_ID'],
        password    = env['ZERODHA_PASSWORD'],
        totp_secret = totp_secret,
    )

    if print_only:
        print(token)
    else:
        _write_token(token)
        print('\n✅ Done. Run ./start.sh to launch the dashboard.')


if __name__ == '__main__':
    main()
