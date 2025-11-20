# GitHub Actions Setup Guide

## Overview

This project uses GitHub Actions for cloud automation of:
- **Paper Trading**: Runs during market hours (9:15 AM - 3:30 PM IST)
- **AI Training**: Trains models on historical data periodically
- **Manual Triggers**: Run jobs on-demand
- **API Triggers**: Trigger via webhooks

## Initial Setup

### 1. Add Secrets to GitHub Repository

Go to your GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**

Add these secrets:
- `KITE_API_KEY` - Your Zerodha Kite API key
- `KITE_API_SECRET` - Your Zerodha API secret
- `KITE_ACCESS_TOKEN` - Your access token (optional, can be generated)
- `ZERODHA_USER_ID` - Your Zerodha user ID
- `ZERODHA_PASSWORD` - Your Zerodha password
- `ZERODHA_PIN` - Your Zerodha PIN

### 2. Push the Workflow

```bash
git add .github/workflows/trading-automation.yml
git commit -m "Add GitHub Actions automation"
git push origin main
```

### 3. Enable Actions

1. Go to your repo on GitHub
2. Click **Actions** tab
3. Enable workflows if prompted

## Usage

### Scheduled Runs (Automatic)

The workflow runs automatically:
- **9:15 AM IST** (Market open) - Monday to Friday
- **3:30 PM IST** (Market close) - Monday to Friday

### Manual Trigger

1. Go to **Actions** tab
2. Select **Trading Automation** workflow
3. Click **Run workflow**
4. Choose action:
   - `paper_trade` - Run paper trading only
   - `train_ai` - Train AI models only
   - `both` - Run both

### API Trigger (Webhook)

Trigger via GitHub API:

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer YOUR_GITHUB_TOKEN" \
  https://api.github.com/repos/YOUR_USERNAME/stocks/dispatches \
  -d '{"event_type":"trade-trigger"}'
```

Event types:
- `trade-trigger` - Runs paper trading
- `train-trigger` - Trains AI models

## Workflow Features

### AI Training Job
- Installs Python dependencies
- Trains AI models on historical data
- Saves trained models as artifacts (30-day retention)
- Runs on manual trigger or API call

### Paper Trading Job
- Runs during scheduled market hours
- Downloads latest trained AI models
- Executes paper trading for 1 hour
- Uploads trading logs as artifacts (90-day retention)
- Times out after 1 hour (configurable)

## Artifacts

### AI Models
- **Location**: Artifacts → `ai-models-{run-number}`
- **Retention**: 30 days
- **Contents**: Trained model files from `ai_data/`

### Trading Logs
- **Location**: Artifacts → `trading-logs-{run-number}`
- **Retention**: 90 days
- **Contents**: All logs from `data/logs/`

## Customization

### Change Schedule

Edit `.github/workflows/trading-automation.yml`:

```yaml
schedule:
  - cron: '45 3 * * 1-5'  # 9:15 AM IST
  - cron: '0 10 * * 1-5'  # 3:30 PM IST
```

Cron format: `minute hour day month day-of-week`

Use [crontab.guru](https://crontab.guru/) to generate schedules.

### Change Trading Duration

Modify timeout in paper trading job:

```yaml
run: |
  timeout 3600 python3 scripts/paper_trade.py || true
```

`3600` = 1 hour (in seconds)

### Add Notifications

#### Slack Notification

Add to workflow steps:

```yaml
- name: Notify Slack
  if: always()
  uses: slackapi/slack-github-action@v1
  with:
    webhook-url: ${{ secrets.SLACK_WEBHOOK_URL }}
    payload: |
      {
        "text": "Trading run completed: ${{ job.status }}"
      }
```

#### Discord Notification

```yaml
- name: Notify Discord
  if: always()
  run: |
    curl -X POST ${{ secrets.DISCORD_WEBHOOK_URL }} \
      -H "Content-Type: application/json" \
      -d '{"content":"Trading run completed: ${{ job.status }}"}'
```

## Monitoring

### View Workflow Runs

1. Go to **Actions** tab
2. Click on a workflow run
3. View job logs and artifacts

### Download Logs

1. Click on completed workflow run
2. Scroll to **Artifacts** section
3. Download `trading-logs-{number}.zip`

### Check Job Status

Green checkmark ✅ = Success
Red X ❌ = Failed
Yellow dot 🟡 = In progress

## Cost

### Public Repository
- **Free unlimited minutes** ✨
- No charges for public repos

### Private Repository
- **2,000 free minutes/month** (Linux runners)
- After free tier: ~$0.008 per minute
- **Estimated cost**: 
  - 2 runs/day × 5 days = 10 runs/week
  - ~10 min/run = 100 min/week = 400 min/month
  - **Well within free tier!** ✅

## Troubleshooting

### Workflow not running?

1. Check repo **Settings → Actions → General**
2. Ensure "Allow all actions" is enabled
3. Verify secrets are added correctly

### Jobs failing?

1. Check job logs in Actions tab
2. Verify API credentials are valid
3. Check if Zerodha API is accessible
4. Ensure `requirements.txt` has all dependencies

### Access token expired?

Update `KITE_ACCESS_TOKEN` secret with new token:
1. Generate new token locally: `python3 scripts/get_token.py`
2. Update secret in GitHub repo settings

## Best Practices

1. **Start with Manual Runs**: Test manually before enabling schedule
2. **Monitor First Week**: Watch logs daily for the first week
3. **Set Alerts**: Configure Slack/Discord notifications
4. **Review Artifacts**: Download and review trading logs weekly
5. **Update Models**: Retrain AI models weekly or monthly
6. **Rotate Tokens**: Update access tokens before expiry

## Advanced: Cloud Storage Integration

To persist AI models across runs, integrate with cloud storage:

### AWS S3 Example

Add to workflow:

```yaml
- name: Upload models to S3
  uses: aws-actions/configure-aws-credentials@v4
  with:
    aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
    aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
    aws-region: us-east-1

- name: Sync to S3
  run: aws s3 sync ai_data/ s3://your-bucket/ai-models/
```

### Google Cloud Storage Example

```yaml
- name: Upload to GCS
  uses: google-github-actions/upload-cloud-storage@v2
  with:
    credentials: ${{ secrets.GCP_CREDENTIALS }}
    path: ai_data/
    destination: your-bucket/ai-models/
```

## Security Notes

⚠️ **Important Security Practices**:

1. **Never commit secrets** to git
2. **Use repository secrets** for all credentials
3. **Limit workflow permissions** in repo settings
4. **Review workflow logs** for sensitive data leaks
5. **Enable branch protection** for main branch
6. **Use environment protection rules** for production

## Support

- **GitHub Actions Docs**: https://docs.github.com/actions
- **Workflow Syntax**: https://docs.github.com/actions/reference/workflow-syntax-for-github-actions
- **Community Forum**: https://github.community/

---

**Status**: ✅ Ready to use
**Last Updated**: 2025-11-20
