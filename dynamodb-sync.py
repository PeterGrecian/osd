#!/usr/bin/env python3
"""
DynamoDB to OpenSearch sync script
Scans DynamoDB tables and pushes them to OpenSearch
"""

import boto3
import requests
import json
from datetime import datetime
from decimal import Decimal
import time

# Configuration
OPENSEARCH_URL = "https://localhost:9200"
OPENSEARCH_USER = "admin"
OPENSEARCH_PASSWORD = "Admin123!@Secure"
AWS_REGION = "eu-west-1"

# DynamoDB tables to sync
TABLES = [
    "cv-access-logs",
    "gardencam-commands",
    "gardencam-deletion-plans",
    "gardencam-page-timing",
    "gardencam-stats",
    "gardencam-video-metadata",
    "hits",
    "k2-bus-arrivals",
    "k2-bus-arrivals_buses",
    "k2-bus-arrivals_movements",
    "k2-bus-arrivals_stops",
    "lambda-execution-logs",
]

class DecimalEncoder(json.JSONEncoder):
    """Handle Decimal types from DynamoDB"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def scan_dynamodb_table(table_name, limit=None):
    """Scan entire DynamoDB table"""
    dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
    table = dynamodb.Table(table_name)

    items = []
    try:
        response = table.scan()
        items.extend(response.get('Items', []))

        # Handle pagination
        while 'LastEvaluatedKey' in response:
            if limit and len(items) >= limit:
                break
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))

        if limit:
            items = items[:limit]

        return items
    except Exception as e:
        print(f"  Error scanning {table_name}: {e}")
        return []

def push_to_opensearch(items, table_name):
    """Push DynamoDB items to OpenSearch using bulk API"""
    if not items:
        return 0

    # Build bulk request
    bulk_data = []
    base_index_name = f"dynamodb-{table_name.lower().replace('_', '-')}"

    for i, item in enumerate(items):
        # Look for timestamp fields in the data
        timestamp_value = None
        timestamp_field = None
        for ts_field in ['timestamp', 'created_at', 'createdAt', 'date', 'time', 'eventTime', 'updated_at', 'updatedAt']:
            if ts_field in item:
                timestamp_field = ts_field
                timestamp_value = item[ts_field]
                break

        # Parse timestamp and determine index name
        event_date = None
        if timestamp_value:
            try:
                # Handle different timestamp formats
                if isinstance(timestamp_value, (int, float)):
                    # Unix timestamp (seconds or milliseconds)
                    if timestamp_value > 10000000000:  # Milliseconds
                        event_date = datetime.fromtimestamp(timestamp_value / 1000)
                    else:  # Seconds
                        event_date = datetime.fromtimestamp(timestamp_value)
                elif isinstance(timestamp_value, str):
                    # ISO format or other string formats
                    from dateutil import parser
                    event_date = parser.parse(timestamp_value)
            except:
                pass

        # Use dated index if we have a timestamp, otherwise undated
        if event_date:
            index_name = f"{base_index_name}-{event_date.strftime('%Y.%m.%d')}"
        else:
            index_name = base_index_name

        # Generate a unique ID
        doc_id = None
        for key_field in ['id', 'pk', 'key', timestamp_field if timestamp_field else 'xxx']:
            if key_field and key_field in item:
                doc_id = str(item[key_field])
                break
        if not doc_id:
            doc_id = f"{table_name}-{i}"

        # Index action
        index_action = {
            "index": {
                "_index": index_name,
                "_id": doc_id
            }
        }

        # Add metadata
        doc = json.loads(json.dumps(item, cls=DecimalEncoder))
        doc['_table'] = table_name
        doc['_synced_at'] = datetime.now().isoformat()

        # Add @timestamp if we found a timestamp
        if event_date:
            doc['@timestamp'] = event_date.isoformat()

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
                print(f"  ✓ Pushed {len(items)} items to {index_name}")
                return len(items)
            else:
                errors = sum(1 for item in result['items'] if item.get('index', {}).get('error'))
                success = len(items) - errors
                print(f"  ⚠ Pushed {success}/{len(items)} items to {index_name} ({errors} errors)")
                return success
        else:
            print(f"  ✗ Error pushing to OpenSearch: {response.status_code}")
            return 0
    except Exception as e:
        print(f"  ✗ Error pushing to OpenSearch: {e}")
        return 0

def get_table_info(table_name):
    """Get table item count"""
    try:
        dynamodb = boto3.client('dynamodb', region_name=AWS_REGION)
        response = dynamodb.describe_table(TableName=table_name)
        return response['Table']['ItemCount']
    except:
        return None

def sync_tables(limit_per_table=None):
    """Sync all DynamoDB tables to OpenSearch"""
    print(f"DynamoDB to OpenSearch Sync")
    print(f"Region: {AWS_REGION}")
    print(f"Tables: {len(TABLES)}\n")

    total_items = 0
    for table_name in TABLES:
        print(f"Processing {table_name}...")

        # Get table size
        item_count = get_table_info(table_name)
        if item_count is not None:
            print(f"  Table has ~{item_count} items")

        # Scan table
        items = scan_dynamodb_table(table_name, limit=limit_per_table)

        if items:
            pushed = push_to_opensearch(items, table_name)
            total_items += pushed
        else:
            print(f"  No items in {table_name}")

        print()

    print(f"Total: {total_items} items synced across {len(TABLES)} tables")
    return total_items

if __name__ == "__main__":
    import sys
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # Optional: limit items per table for testing
    limit = None
    if len(sys.argv) > 1:
        limit = int(sys.argv[1])
        print(f"Limiting to {limit} items per table\n")

    sync_tables(limit_per_table=limit)
