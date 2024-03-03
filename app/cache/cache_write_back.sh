#!/bin/bash

cd /home/ec2-user/quiz-backend/
source venv/bin/activate
cd app
python3 -m cache.cache_write_back >> /home/ec2-user/quiz-backend/logs/cache_write_back.log 2>&1