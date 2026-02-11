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

## Troubleshooting

```bash
# Check service status
docker-compose ps

# View OpenSearch logs
docker-compose logs opensearch

# Test OpenSearch connection
curl -k -u admin:Admin123! https://localhost:9200

# Check indices
curl -k -u admin:Admin123! https://localhost:9200/_cat/indices?v
```
