#!/bin/bash
# Quick launch script for dashboard
cd "$(dirname "$0")/.."
python3 -m src.web.app
