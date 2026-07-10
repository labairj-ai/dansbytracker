#!/bin/bash
cd /Users/ai_lab/dansbytracker
source venv/bin/activate
python dansbytracker.py >> out/dansbytracker.log 2>&1
