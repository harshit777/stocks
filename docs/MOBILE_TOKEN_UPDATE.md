# 📱 Mobile Token Update Guide

Update your Zerodha access token from your phone every morning before market opens!

---

## Overview

This guide helps you run a simple script on your **phone** to:
1. Login to Zerodha (with your PIN/2FA)
2. Generate a fresh access token
3. Update GitHub secrets automatically
4. Let your trading bot run all day

**Time required:** 30-60 seconds each morning

---

## Setup (One-Time)

### For Android (Termux)

1. **Install Termux** from F-Droid (NOT Google Play):
   - Download: https://f-droid.org/en/packages/com.termux/

2. **Install required packages:**
   ```bash
   pkg update
   pkg install git curl openssh gh
   ```

3. **Setup GitHub authentication:**
   ```bash
   gh auth login
   # Follow the prompts
   ```

4. **Clone your repo:**
   ```bash
   cd ~
   git clone https://github.com/YOUR_USERNAME/stocks.git
   cd stocks
   ```

5. **Create config file:**
   ```bash
   cat > .mobile_token_config << 'EOF'
   KITE_API_KEY="your_api_key_here"
   KITE_API_SECRET="your_api_secret_here"
   GITHUB_REPO="your_username/stocks"
   EOF
   chmod 600 .mobile_token_config
   ```

---

### For iPhone (iSH Shell)

1. **Install iSH** from App Store:
   - Download: https://apps.apple.com/us/app/ish-shell/id1436902243

2. **Install required packages:**
   ```bash
   apk update
   apk add git curl openssh bash coreutils github-cli
   ```

3. **Setup GitHub authentication:**
   ```bash
   gh auth login
   # Follow the prompts
   ```

4. **Clone your repo:**
   ```bash
   cd ~
   git clone https://github.com/YOUR_USERNAME/stocks.git
   cd stocks
   ```

5. **Create config file:**
   ```bash
   cat > .mobile_token_config << 'EOF'
   KITE_API_KEY="your_api_key_here"
   KITE_API_SECRET="your_api_secret_here"
   GITHUB_REPO="your_username/stocks"
   EOF
   chmod 600 .mobile_token_config
   ```

---

### Alternative: iOS Shortcuts (No Terminal App)

If you don't want to install a terminal app, you can use iOS Shortcuts:

**Coming soon** - A simplified URL-based approach using iOS Shortcuts

---

## Daily Usage

### Run the Script (Every Trading Day Before 9:15 AM)

**Android (Termux):**
```bash
cd ~/stocks
./scripts/mobile_update_token.sh
```

**iPhone (iSH):**
```bash
cd ~/stocks
bash scripts/mobile_update_token.sh
```

### What Happens:

1. **Script opens Zerodha login** in your browser
2. **You login** with your credentials + PIN/2FA
3. **You copy the redirect URL** and paste it back
4. **Script generates token** and updates GitHub automatically
5. **Done!** Your bot will trade all day

---

## Step-by-Step Walkthrough

### Step 1: Run Script
```bash
./scripts/mobile_update_token.sh
```

Output:
```
================================
🔐 Zerodha Token Updater (Mobile)
================================

✅ Loaded saved configuration
ℹ️  Running on Android (Termux)

================================
Checking Dependencies
================================

✅ GitHub CLI found
```

### Step 2: Login to Zerodha

The script opens this URL automatically:
```
https://kite.zerodha.com/connect/login?api_key=YOUR_KEY
```

- Login with your Zerodha credentials
- Enter your PIN/2FA
- You'll be redirected to something like:
  ```
  http://127.0.0.1/?request_token=ABC123XYZ&action=login&status=success
  ```

### Step 3: Paste Redirect URL

Copy the **entire redirect URL** and paste it back:
```
================================
Step 2: Get Request Token
================================

ℹ️  After logging in, you'll be redirected to a URL
ℹ️  The URL will look like:
  http://127.0.0.1/?request_token=XXXXXX&action=login&status=success

Paste the FULL redirect URL here: [paste here]
```

### Step 4: Token Generated!

```
================================
Step 3: Generate Access Token
================================

ℹ️  Calling Zerodha API...
✅ Access token generated!

Token: your_access_token_here
```

### Step 5: GitHub Updated

```
================================
Step 4: Update GitHub Secret
================================

ℹ️  Updating GitHub secret via CLI...
✅ GitHub secret updated successfully!

================================
✅ All Done!
================================

✅ Token is valid until end of trading day
ℹ️  Run this script again tomorrow morning before 9:15 AM
```

---

## Troubleshooting

### "curl is not installed"

**Termux:**
```bash
pkg install curl
```

**iSH:**
```bash
apk add curl
```

### "GitHub CLI (gh) not found"

**Termux:**
```bash
pkg install gh
gh auth login
```

**iSH:**
```bash
apk add github-cli
gh auth login
```

### "GitHub CLI not authenticated"

```bash
gh auth login
# Choose: GitHub.com
# Choose: HTTPS
# Choose: Login with a browser
# Follow the prompts
```

### "Failed to generate access token"

Check:
1. API key is correct
2. API secret is correct
3. Request token was copied correctly (entire URL)
4. Token wasn't already used (tokens are one-time use)

**Solution:** Run the script again from the start

### Script won't run / Permission denied

```bash
chmod +x scripts/mobile_update_token.sh
```

---

## Manual Update (If Script Fails)

If the script fails for any reason, you can still update manually:

1. **Generate token** on your computer:
   ```bash
   python3 scripts/update_github_token.py
   ```

2. **Update GitHub secret manually:**
   - Go to: https://github.com/YOUR_USERNAME/stocks/settings/secrets/actions
   - Click on `KITE_ACCESS_TOKEN`
   - Paste new token
   - Click "Update secret"

---

## Tips & Best Practices

### 🌅 Morning Routine (8:45-9:00 AM IST)

1. Open Termux/iSH
2. Run: `cd ~/stocks && ./scripts/mobile_update_token.sh`
3. Login when prompted
4. Copy/paste URL
5. Done! Check GitHub Actions starts at 9:15 AM

### 📱 Keep App Open

- **Termux/iSH** might get killed by OS in background
- Run the script with phone **unlocked and app active**
- Takes less than 60 seconds anyway

### 🔐 Security

- Config file is `chmod 600` (only you can read)
- Never share your `.mobile_token_config` file
- GitHub tokens are encrypted in GitHub Secrets
- Access token expires daily anyway

### 🔄 Update Script

Pull latest changes occasionally:
```bash
cd ~/stocks
git pull origin main
```

---

## Advanced: Automation Ideas

### Option 1: Morning Alarm + Widget

Create a phone widget/shortcut that:
1. Triggers at 8:45 AM
2. Opens Termux/iSH
3. Runs the script
4. You just need to handle the login

### Option 2: Desktop Cron Job

If you have a home computer/laptop that's always on:
```bash
# Edit crontab
crontab -e

# Add (runs at 8:30 AM IST on weekdays)
30 3 * * 1-5 cd ~/dev/go/src/github.com/stocks && python3 scripts/update_github_token.py --repo USER/REPO --token $(gh auth token)
```

**Note:** Still requires manual Zerodha login (can't be fully automated)

### Option 3: Use Phone as Server

Keep an old Android phone at home:
- Install Termux
- Set up the script
- Remote in via SSH when needed
- Run the script remotely

---

## FAQ

### Q: Can this be fully automated?

**A:** No. Zerodha requires manual login with PIN/2FA for security. This is by design and cannot be bypassed.

### Q: What if I miss updating the token?

**A:** No problem! Your GitHub Actions workflow will fail, but:
- No money is lost (it's paper trading)
- Just update the token the next day
- The bot will resume trading

### Q: How long is the token valid?

**A:** Until end of trading day (~3:30 PM IST). You need to regenerate it daily.

### Q: Can I use this on my iPad?

**A:** Yes! iSH works on iPad too. Same instructions as iPhone.

### Q: What if I'm traveling?

**A:** You can:
1. Run the script from your phone anywhere
2. Ask someone to update manually via GitHub website
3. Let it skip a day (paper trading = no real loss)

### Q: Is my data safe on mobile?

**A:** Yes:
- Terminal apps are sandboxed
- Config file is only readable by you
- GitHub tokens are encrypted
- Use a passcode/biometric on your phone

---

## Quick Reference

| Task | Command |
|------|---------|
| **Run script** | `./scripts/mobile_update_token.sh` |
| **Update script** | `git pull origin main` |
| **Check config** | `cat .mobile_token_config` |
| **Re-authenticate GitHub** | `gh auth login` |
| **Manual token gen** | `python3 scripts/update_github_token.py` |

---

## Support

If you encounter issues:

1. Check the [Troubleshooting](#troubleshooting) section
2. Review GitHub Actions logs: https://github.com/YOUR_USERNAME/stocks/actions
3. Check main setup guide: [GITHUB_ACTIONS_SETUP.md](../GITHUB_ACTIONS_SETUP.md)

---

## Summary

✅ **One-time setup:** Install app + configure (10 minutes)  
✅ **Daily update:** Run script from phone (30-60 seconds)  
✅ **Fully mobile:** No computer needed  
✅ **Secure:** Your credentials never leave your phone  
✅ **Simple:** Just copy/paste one URL  

Happy trading! 📈
