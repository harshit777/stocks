#!/bin/bash

# Google Cloud Deployment Script for Trading Bot
# This script builds and deploys the trading bot to Google Cloud Run

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ID="${GCP_PROJECT_ID}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="trading-bot"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if PROJECT_ID is set
if [ -z "$PROJECT_ID" ]; then
    print_error "GCP_PROJECT_ID environment variable is not set"
    echo "Usage: export GCP_PROJECT_ID=your-project-id"
    exit 1
fi

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    print_error "gcloud CLI is not installed"
    echo "Install it from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Set the project
print_status "Setting GCP project to: $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

# Enable required APIs
print_status "Enabling required Google Cloud APIs..."
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable containerregistry.googleapis.com

# Build the Docker image
print_status "Building Docker image..."
gcloud builds submit --tag "$IMAGE_NAME" .

# Check if secrets exist, if not prompt to create them
print_status "Checking for secrets..."

create_secret_if_not_exists() {
    local secret_name=$1
    local secret_description=$2
    
    if ! gcloud secrets describe "$secret_name" &> /dev/null; then
        print_warning "Secret '$secret_name' does not exist"
        read -p "Enter value for $secret_description: " secret_value
        echo -n "$secret_value" | gcloud secrets create "$secret_name" --data-file=-
        print_status "Secret '$secret_name' created"
    else
        print_status "Secret '$secret_name' already exists"
    fi
}

create_secret_if_not_exists "kite-api-key" "Kite API Key"
create_secret_if_not_exists "kite-api-secret" "Kite API Secret"
create_secret_if_not_exists "kite-access-token" "Kite Access Token"

# Deploy to Cloud Run
print_status "Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
    --image "$IMAGE_NAME" \
    --platform managed \
    --region "$REGION" \
    --no-allow-unauthenticated \
    --min-instances 1 \
    --max-instances 1 \
    --cpu 1 \
    --memory 512Mi \
    --timeout 3600 \
    --cpu-throttling=false \
    --set-secrets="KITE_API_KEY=kite-api-key:latest,KITE_API_SECRET=kite-api-secret:latest,KITE_ACCESS_TOKEN=kite-access-token:latest"

# Get the service URL
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format 'value(status.url)')

print_status "Deployment complete!"
print_status "Service URL: $SERVICE_URL"
print_status "Service Name: $SERVICE_NAME"
print_status "Region: $REGION"

echo ""
print_status "To view logs, run:"
echo "gcloud logs tail --service=$SERVICE_NAME --region=$REGION"

echo ""
print_status "To update secrets, run:"
echo "echo -n 'NEW_VALUE' | gcloud secrets versions add SECRET_NAME --data-file=-"

echo ""
print_status "To check service status:"
echo "gcloud run services describe $SERVICE_NAME --region=$REGION"
