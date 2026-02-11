# OpenSearch Dashboards Local Setup

A local OpenSearch + Dashboards stack for ingesting and visualizing CloudWatch and application logs.

## Quick Start

```bash
# Copy environment file
cp .env.example .env

# Edit .env with your settings
nano .env

# Start the stack
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the stack
docker-compose down
```

## Access

- **OpenSearch Dashboards**: http://localhost:5601
- **OpenSearch API**: https://localhost:9200
- Default credentials: `admin` / `Admin123!` (change in .env)

## Ingesting Logs

### Local Application Logs

1. Place log files in the `logs/` directory
2. Fluent Bit will automatically tail and ingest them

### CloudWatch Logs

1. Ensure AWS credentials are configured (`~/.aws/credentials`)
2. Edit `fluent-bit.conf` and uncomment the CloudWatch input section
3. Configure your log group name and region
4. Restart Fluent Bit: `docker-compose restart fluent-bit`

## Configuration

- **docker-compose.yml**: Service definitions
- **fluent-bit.conf**: Log shipping configuration
- **.env**: Environment variables and secrets

## AWS Permissions

For CloudWatch ingestion, ensure your AWS credentials have:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams",
        "logs:GetLogEvents",
        "logs:FilterLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
```

## Tips

- **Memory**: OpenSearch needs at least 2GB RAM. Adjust `OPENSEARCH_JAVA_OPTS` in docker-compose.yml if needed
- **Security**: Change the default password in production
- **Index Management**: Set up Index State Management (ISM) policies to manage data retention
- **Performance**: Use index templates and mapping for better performance

## Index Management

### Viewing Indexes

Use the `bin/indx` script for easy index operations:

```bash
# List all indexes
bin/indx list

# Show summary of all data
bin/indx summary

# Count documents in CloudWatch logs
bin/indx count 'cloudwatch-*'

# View recent CloudWatch logs
bin/indx cloudwatch

# View DynamoDB table
bin/indx dynamodb gardencam-stats

# Show help
bin/indx help
```

### Cleaning Up Old Data

Use `bin/cleanup` to delete old dated indexes:

```bash
# Delete CloudWatch logs older than 30 days
bin/cleanup 30 'cloudwatch-*'

# Delete all dated indexes older than 90 days
bin/cleanup 90

# Delete specific table history older than 7 days
bin/cleanup 7 'dynamodb-gardencam-stats-*'
```

**Note:** Undated indexes (like `dynamodb-hits`) are snapshots and never deleted by cleanup.

## Syncing AWS Data

**Smart sync (recommended):**
```bash
# Auto-detects latest timestamp and syncs from there
./sync-cron.sh

# Or individually:
./cloudwatch-sync.py     # Smart sync from latest log
./dynamodb-sync.py       # Smart sync from latest items
```

How it works:
- Queries OpenSearch for latest @timestamp
- Only syncs data newer than what you have
- No gaps, no duplicates, efficient!

**Force sync (when needed):**
```bash
# Ignore existing data and force sync last N hours
./cloudwatch-sync.py --force 168  # Force last 7 days
./cloudwatch-sync.py 24           # Fallback to 24h if no existing data

# DynamoDB full rescan
./dynamodb-sync.py --force        # Rescan all tables
```

**Note:** Data is NOT auto-synced. Run `./sync-cron.sh` manually when you want fresh data from AWS.

## Troubleshooting

```bash
# Check service status
docker compose ps

# View OpenSearch logs
docker compose logs opensearch

# Test OpenSearch connection
curl -k -u admin:Admin123!@Secure https://localhost:9200

# Check indices (or use: bin/indx list)
curl -k -u admin:Admin123!@Secure https://localhost:9200/_cat/indices?v
```
