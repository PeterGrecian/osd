#!/bin/bash
# Automatic sync script for CloudWatch and DynamoDB
# Smart sync: automatically detects latest data and syncs from there
# Usage: ./sync-now.sh [--watch INTERVAL]
#   --watch INTERVAL  Keep syncing every INTERVAL seconds (default: 300 = 5 min)

cd /home/tot/osd

# Parse arguments
WATCH_MODE=false
INTERVAL=300  # 5 minutes default

while [[ $# -gt 0 ]]; do
  case $1 in
    --watch)
      WATCH_MODE=true
      if [[ $2 =~ ^[0-9]+$ ]]; then
        INTERVAL=$2
        shift
      fi
      shift
      ;;
    *)
      echo "Usage: $0 [--watch INTERVAL]"
      echo "  --watch INTERVAL  Keep syncing every INTERVAL seconds (default: 300)"
      exit 1
      ;;
  esac
done

# Function to run one sync
run_sync() {
  # Track timing
  START_TIME=$(date +%s)

  # Log sync start
  bin/log-operation "sync" "started" "CloudWatch and DynamoDB sync initiated"

  # Smart sync CloudWatch logs (finds latest timestamp automatically)
  echo "$(date): Syncing CloudWatch logs..."
  CW_OUTPUT=$(./cloudwatch-sync.py 2>&1 | tee -a /home/tot/osd/sync.log)
  CW_COUNT=$(echo "$CW_OUTPUT" | grep "^Total:" | awk '{print $2}')

  # Smart sync DynamoDB (only syncs items newer than existing data)
  echo "$(date): Syncing DynamoDB..."
  DB_OUTPUT=$(./dynamodb-sync.py 2>&1 | tee -a /home/tot/osd/sync.log)
  DB_COUNT=$(echo "$DB_OUTPUT" | grep "^Total:" | awk '{print $2}')

  # Calculate duration
  END_TIME=$(date +%s)
  DURATION=$((END_TIME - START_TIME))

  # Log sync completion with duration
  bin/log-operation "sync" "completed" "CloudWatch: ${CW_COUNT:-0} events, DynamoDB: ${DB_COUNT:-0} items, Duration: ${DURATION}s"

  echo "$(date): Sync complete (${DURATION}s)"
  echo "---"
}

# Run sync once or in watch mode
if [ "$WATCH_MODE" = true ]; then
  echo "Watch mode enabled: syncing every ${INTERVAL}s"
  echo "Press Ctrl+C to stop"
  echo ""

  # Trap Ctrl+C for clean exit
  trap 'echo ""; echo "Stopping watch mode..."; bin/log-operation "sync" "watch-stopped" "Watch mode stopped by user"; exit 0' INT

  # Log watch mode start
  bin/log-operation "sync" "watch-started" "Watch mode started with ${INTERVAL}s interval"

  while true; do
    run_sync
    echo "Next sync in ${INTERVAL}s... (Ctrl+C to stop)"
    sleep "$INTERVAL"
    echo ""
  done
else
  run_sync
fi
