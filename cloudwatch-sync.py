#!/usr/bin/env python3
"""
CloudWatch to OpenSearch sync script
Fetches logs from CloudWatch and pushes them to OpenSearch
Smart sync: queries OpenSearch for latest timestamp and syncs from there
"""

import boto3
import requests
import json
from datetime import datetime, timedelta
import time
import os
import sys

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
    now = datetime.now()

    for event in events:
        # Use event timestamp for index date (not current date)
        event_date = datetime.fromtimestamp(event['timestamp'] / 1000)

        # Calculate age of the event
        age_days = (now - event_date).days

        # Use monthly index for old data (30+ days), daily for recent data
        if age_days >= 30:
            index_name = f"cloudwatch-{event_date.strftime('%Y.%m')}"
        else:
            index_name = f"cloudwatch-{event_date.strftime('%Y.%m.%d')}"

        # Index action
        index_action = {
            "index": {
                "_index": index_name,
                "_id": f"{log_group}-{event['eventId']}"
            }
        }

        # Document
        doc = {
            "@timestamp": event_date.isoformat(),
            "message": event['message'],
            "log_group": log_group,
            "log_stream": event.get('logStreamName', ''),
            "ingestion_time": event.get('ingestionTime', event['timestamp']),
        }

        # Extract clean lambda/service name for easier visualization
        if log_group.startswith('/aws/lambda/'):
            doc['lambda_name'] = log_group.replace('/aws/lambda/', '')
        elif log_group.startswith('/aws/api_gw/'):
            doc['service_name'] = log_group.replace('/aws/api_gw/', '')
            doc['lambda_name'] = 'api-gw/' + doc['service_name']
        else:
            doc['lambda_name'] = log_group

        # Extract duration from REPORT messages
        msg = event['message']
        if 'REPORT RequestId:' in msg and 'Duration:' in msg:
            try:
                # Extract duration value (e.g., "Duration: 1400.82 ms")
                import re
                match = re.search(r'Duration:\s+([\d.]+)\s+ms', msg)
                if match:
                    doc['duration_ms'] = float(match.group(1))
                    doc['log_type'] = 'REPORT'
            except:
                pass
        elif 'START RequestId:' in msg:
            doc['log_type'] = 'START'
        elif 'END RequestId:' in msg:
            doc['log_type'] = 'END'

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

def get_latest_timestamp():
    """Get the latest @timestamp from existing CloudWatch indexes"""
    try:
        response = requests.post(
            f"{OPENSEARCH_URL}/cloudwatch-*/_search",
            auth=(OPENSEARCH_USER, OPENSEARCH_PASSWORD),
            headers={"Content-Type": "application/json"},
            json={
                "size": 0,
                "aggs": {
                    "max_timestamp": {
                        "max": {
                            "field": "@timestamp"
                        }
                    }
                }
            },
            verify=False
        )

        if response.status_code == 200:
            result = response.json()
            max_ts = result.get('aggregations', {}).get('max_timestamp', {}).get('value')
            if max_ts:
                # Convert from milliseconds to datetime
                return datetime.fromtimestamp(max_ts / 1000)
        return None
    except Exception as e:
        print(f"Could not get latest timestamp: {e}")
        return None

def sync_logs(hours_back=None, force_hours=False):
    """Sync logs from the last N hours, or from last sync if hours_back not specified"""
    end_time = datetime.now()

    if hours_back and force_hours:
        # User explicitly specified hours, use that
        start_time = end_time - timedelta(hours=hours_back)
        print(f"Syncing logs from {start_time} to {end_time} (forced {hours_back}h)")
    else:
        # Try to get latest timestamp from OpenSearch
        latest = get_latest_timestamp()

        if latest:
            # Subtract 5 minutes to ensure we don't miss anything due to timing
            start_time = latest - timedelta(minutes=5)
            hours_since = (end_time - start_time).total_seconds() / 3600
            print(f"Smart sync: Latest log is {latest}")
            print(f"Syncing logs from {start_time} to {end_time} ({hours_since:.1f}h)")
        elif hours_back:
            # No existing data, use provided hours
            start_time = end_time - timedelta(hours=hours_back)
            print(f"No existing logs found. Syncing last {hours_back} hours")
            print(f"Syncing logs from {start_time} to {end_time}")
        else:
            # No existing data and no hours specified, default to 24h
            hours_back = 24
            start_time = end_time - timedelta(hours=hours_back)
            print(f"No existing logs found. Syncing last {hours_back} hours (default)")
            print(f"Syncing logs from {start_time} to {end_time}")

    start_time_ms = int(start_time.timestamp() * 1000)
    end_time_ms = int(end_time.timestamp() * 1000)

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
    # Disable SSL warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    print(f"CloudWatch to OpenSearch Sync")
    print(f"Region: {AWS_REGION}")
    print(f"Log groups: {len(LOG_GROUPS)}")
    print()

    # Parse arguments
    force_hours = False
    hours = None

    if len(sys.argv) > 1:
        if sys.argv[1] == '--force' and len(sys.argv) > 2:
            force_hours = True
            hours = int(sys.argv[2])
            print(f"Force mode: Syncing last {hours} hours (ignoring existing data)")
        else:
            hours = int(sys.argv[1])

    sync_logs(hours_back=hours, force_hours=force_hours)
