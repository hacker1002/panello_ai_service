# Deployment Guide

## Prerequisites

- Python 3.8+
- Docker (optional)
- Supabase project
- Google Cloud account with Gemini API access

## Environment Configuration

### 1. Create Environment File

```bash
cp .env.example .env
```

### 2. Configure Variables

```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key

# Google AI
GOOGLE_API_KEY=your-google-api-key

# Optional
ENVIRONMENT=production
LOG_LEVEL=INFO
```

## Deployment Options

### Option 1: Direct Deployment

```bash
# Install dependencies
pip install -r requirements.txt

# Run with Gunicorn
gunicorn main:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile -
```

### Option 2: Docker

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
```

Build and run:
```bash
docker build -t panello-ai-service .
docker run -p 8000:8000 --env-file .env panello-ai-service
```

### Option 3: Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

Run:
```bash
docker-compose up -d
```

### Option 4: Kubernetes

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: panello-ai-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: panello-ai-service
  template:
    metadata:
      labels:
        app: panello-ai-service
    spec:
      containers:
      - name: api
        image: panello-ai-service:latest
        ports:
        - containerPort: 8000
        env:
        - name: SUPABASE_URL
          valueFrom:
            secretKeyRef:
              name: panello-secrets
              key: supabase-url
        - name: SUPABASE_KEY
          valueFrom:
            secretKeyRef:
              name: panello-secrets
              key: supabase-key
        - name: GOOGLE_API_KEY
          valueFrom:
            secretKeyRef:
              name: panello-secrets
              key: google-api-key
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: panello-ai-service
spec:
  selector:
    app: panello-ai-service
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

## Database Setup

### 1. Run Migrations

Apply the streaming messages migration to your Supabase database:

```sql
-- Execute in Supabase SQL Editor
-- Copy content from: 
-- ai-mentor-panello/supabase/migrations/20250905000000_create_streaming_messages_system.sql
```

### 2. Enable Real-time

```sql
-- Enable real-time for streaming_messages
ALTER PUBLICATION supabase_realtime ADD TABLE streaming_messages;

-- Grant permissions
GRANT ALL ON streaming_messages TO authenticated, anon;
```

### 3. Create Indexes

```sql
-- Performance indexes
CREATE INDEX idx_streaming_room_thread_active 
ON streaming_messages(room_id, thread_id, is_complete) 
WHERE is_complete = FALSE;

CREATE INDEX idx_messages_room_thread 
ON messages(room_id, thread_id, created_at DESC);
```

## Reverse Proxy (Nginx)

```nginx
server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## SSL/TLS with Certbot

```bash
# Install Certbot
sudo apt-get update
sudo apt-get install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d api.example.com

# Auto-renewal
sudo certbot renew --dry-run
```

## Monitoring

### Health Check Endpoint

```bash
curl http://localhost:8000/health
```

### Prometheus Metrics (Optional)

```python
# Add to requirements.txt
prometheus-fastapi-instrumentator

# Add to main.py
from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator().instrument(app).expose(app)
```

### Logging

Configure logging in production:

```python
# core/config.py
import logging

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/var/log/panello/api.log')
    ]
)
```

## Performance Tuning

### 1. Gunicorn Workers

```bash
# Calculate workers: (2 x CPU cores) + 1
gunicorn main:app -w 9  # For 4 CPU cores
```

### 2. Connection Pooling

```python
# In core/supabase_client.py
from supabase import create_client, Client
from functools import lru_cache

@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    return create_client(
        settings.supabase_url,
        settings.supabase_key,
        options={
            'db': {
                'pool_min': 5,
                'pool_max': 20
            }
        }
    )
```

### 3. Rate Limiting

```python
# Add to requirements.txt
slowapi

# Add to main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"]
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Apply to endpoints
@router.post("/chat/stream")
@limiter.limit("10/minute")
async def chat_stream(request: Request, ...):
    ...
```

## Security Checklist

- [ ] Environment variables properly configured
- [ ] SSL/TLS enabled
- [ ] Rate limiting implemented
- [ ] Input validation active
- [ ] Supabase RLS policies configured
- [ ] API keys rotated regularly
- [ ] Monitoring and alerting setup
- [ ] Regular security updates
- [ ] Backup strategy in place

## Troubleshooting

### Common Issues

1. **Connection refused**
   ```bash
   # Check if service is running
   systemctl status panello-ai
   # Check logs
   journalctl -u panello-ai -f
   ```

2. **Database connection errors**
   ```bash
   # Verify Supabase URL and key
   curl $SUPABASE_URL/rest/v1/ -H "apikey: $SUPABASE_KEY"
   ```

3. **AI API errors**
   ```bash
   # Test Gemini API
   curl -X POST https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent \
     -H "x-goog-api-key: $GOOGLE_API_KEY"
   ```

## Scaling Considerations

1. **Horizontal Scaling**: Add more service instances behind load balancer
2. **Database Optimization**: Use read replicas for heavy read operations
3. **Caching**: Implement Redis for frequently accessed data
4. **CDN**: Use CloudFlare or similar for static assets
5. **Queue System**: Add RabbitMQ/Redis for async task processing

## Maintenance

### Regular Tasks

- **Daily**: Check error logs, monitor performance metrics
- **Weekly**: Review and clean up old streaming messages
- **Monthly**: Update dependencies, rotate API keys
- **Quarterly**: Security audit, performance review

### Cleanup Script

```bash
#!/bin/bash
# cleanup.sh - Run daily via cron

# Cleanup old streaming messages
psql $DATABASE_URL -c "SELECT cleanup_old_streaming_messages(24);"

# Rotate logs
logrotate /etc/logrotate.d/panello-ai

# Clear temp files
find /tmp -name "panello-*" -mtime +7 -delete
```

Add to crontab:
```bash
0 2 * * * /opt/panello/cleanup.sh
```