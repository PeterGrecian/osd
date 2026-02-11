#!/bin/bash
# Automatic sync script for CloudWatch and DynamoDB

cd /home/tot/osd

# Sync last 1 hour of CloudWatch logs
echo "$(date): Syncing CloudWatch logs..."
./cloudwatch-sync.py 1 >> /home/tot/osd/sync.log 2>&1

# Sync DynamoDB (only new/changed items will be indexed)
echo "$(date): Syncing DynamoDB..."
./dynamodb-sync.py >> /home/tot/osd/sync.log 2>&1

echo "$(date): Sync complete"
echo "---"
