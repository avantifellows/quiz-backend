#!/bin/bash

cd /home/ec2-user/quiz-backend/
source venv/bin/activate
cd app/cache
python3 cache_write_back.py >> /home/ec2-user/quiz-backend/logs/cache_write_back.log 2>&1