#!/bin/bash
# Automatic sync script for CloudWatch and DynamoDB
# Smart sync: automatically detects latest data and syncs from there

cd /home/tot/osd

# Smart sync CloudWatch logs (finds latest timestamp automatically)
echo "$(date): Syncing CloudWatch logs..."
./cloudwatch-sync.py >> /home/tot/osd/sync.log 2>&1

# Smart sync DynamoDB (only syncs items newer than existing data)
echo "$(date): Syncing DynamoDB..."
./dynamodb-sync.py >> /home/tot/osd/sync.log 2>&1

echo "$(date): Sync complete"
echo "---"
