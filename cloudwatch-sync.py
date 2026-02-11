#!/usr/bin/env python3
"""
CloudWatch to OpenSearch sync script
Fetches logs from CloudWatch and pushes them to OpenSearch
"""

import boto3
import requests
import json
from datetime import datetime, timedelta
import time
import os

# Configuration
OPENSEARCH_URL = "https://localhost:9200"
OPENSEARCH_USER = "admin"
OPENSEARCH_PASSWORD = "Admin123!@Secure"
AWS_REGION = "eu-west-1"

# Log groups to sync
LOG_GROUPS = [
    "/aws/lambda/cvdev",
    "/aws/lambda/t3",
    "/aws/lambda/t3-trains",
    "/aws/lambda/gardencam-storage-summary",
    "/aws/lambda/gardencam-averaging",
    "/aws/lambda/gardencam-image-culling",
    "/aws/lambda/gardencam-timelapse-generator",
    "/aws/lambda/gela602ca3",
    "/aws/lambda/cvterraform",
    "/aws/lambda/HelloCdkStack-HelloWorldFunctionB2AB6E79-2WCr3l8JiYUE",
    "/aws/lambda/my-api-handler",
    "/aws/lambda/cv-experimental",
    "/aws/api_gw/cvdev",
    "/aws/api_gw/cv-experimental",
    "/aws/api_gw/example-http-api",
    "/aws/api_gw/my-api-api",
]

def get_cloudwatch_logs(log_group, start_time_ms, end_time_ms=None):
    """Fetch logs from CloudWatch"""
    client = boto3.client('logs', region_name=AWS_REGION)

    if end_time_ms is None:
        end_time_ms = int(time.time() * 1000)

    try:
        response = client.filter_log_events(
            logGroupName=log_group,
            startTime=start_time_ms,
            endTime=end_time_ms,
            limit=1000
        )
        return response.get('events', [])
    except Exception as e:
        print(f"Error fetching logs from {log_group}: {e}")
        return []

def push_to_opensearch(events, log_group):
    """Push events to OpenSearch using bulk API"""
    if not events:
        return 0

    # Build bulk request
    bulk_data = []
    for event in events:
        # Index action
        index_action = {
            "index": {
                "_index": f"cloudwatch-{datetime.now().strftime('%Y.%m.%d')}",
                "_id": f"{log_group}-{event['eventId']}"
            }
        }

        # Document
        doc = {
            "@timestamp": datetime.fromtimestamp(event['timestamp'] / 1000).isoformat(),
            "message": event['message'],
            "log_group": log_group,
            "log_stream": event.get('logStreamName', ''),
            "ingestion_time": event.get('ingestionTime', event['timestamp']),
        }

        # Try to parse JSON messages
        try:
            if event['message'].startswith('{'):
                parsed = json.loads(event['message'])
                doc['parsed'] = parsed
        except:
            pass

        bulk_data.append(json.dumps(index_action))
        bulk_data.append(json.dumps(doc))

    bulk_body = '\n'.join(bulk_data) + '\n'

    # Send to OpenSearch
    try:
        response = requests.post(
            f"{OPENSEARCH_URL}/_bulk",
            auth=(OPENSEARCH_USER, OPENSEARCH_PASSWORD),
            headers={"Content-Type": "application/x-ndjson"},
            data=bulk_body,
            verify=False
        )

        if response.status_code == 200:
            result = response.json()
            if not result.get('errors'):
                return len(events)
            else:
                print(f"Some errors during bulk insert: {result}")
                return len([item for item in result['items'] if not item.get('index', {}).get('error')])
        else:
            print(f"Error pushing to OpenSearch: {response.status_code} - {response.text}")
            return 0
    except Exception as e:
        print(f"Error pushing to OpenSearch: {e}")
        return 0

def sync_logs(hours_back=24):
    """Sync logs from the last N hours"""
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours_back)

    start_time_ms = int(start_time.timestamp() * 1000)
    end_time_ms = int(end_time.timestamp() * 1000)

    print(f"Syncing logs from {start_time} to {end_time}")

    total_events = 0
    for log_group in LOG_GROUPS:
        print(f"Processing {log_group}...")
        events = get_cloudwatch_logs(log_group, start_time_ms, end_time_ms)

        if events:
            pushed = push_to_opensearch(events, log_group)
            total_events += pushed
            print(f"  Pushed {pushed} events from {log_group}")
        else:
            print(f"  No events in {log_group}")

    print(f"\nTotal: {total_events} events synced")
    return total_events

if __name__ == "__main__":
    import sys

    # Disable SSL warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24

    print(f"CloudWatch to OpenSearch Sync")
    print(f"Region: {AWS_REGION}")
    print(f"Log groups: {len(LOG_GROUPS)}")
    print(f"Time range: Last {hours} hours\n")

    sync_logs(hours)
