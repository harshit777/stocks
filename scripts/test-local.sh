#!/bin/bash

# Local Docker Testing Script
# Test your trading bot container locally before deploying to Google Cloud

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_warning "Docker is not installed"
    echo "Install it from: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    print_warning ".env file not found"
    echo "Create a .env file with your credentials"
    exit 1
fi

IMAGE_NAME="trading-bot-local"

# Build the image
print_status "Building Docker image..."
docker build -t "$IMAGE_NAME" .

# Run the container
print_status "Running container locally..."
docker run --rm -it --env-file .env "$IMAGE_NAME"

print_status "Container stopped"
