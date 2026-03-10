# Production Setup Guide

Complete guide for deploying Google Workspace ADK to production.

## Prerequisites

- Google Cloud Project with billing enabled
- Google Workspace domain (for Service Account delegation)
- Docker installed locally
- `gcloud` CLI installed and authenticated

## 1. Database Setup

### Option A: PostgreSQL (Recommended for flexibility)

```bash
# Create Cloud SQL PostgreSQL instance
gcloud sql instances create workspace-adk-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1

# Create database
gcloud sql databases create adk_sessions \
  --instance=workspace-adk-db

# Run migrations
psql $DATABASE_URL < migrations/001_create_sessions_table.sql
```

### Option B: Firestore (Recommended for simplicity)

```bash
# Enable Firestore API
gcloud services enable firestore.googleapis.com

# Create Firestore database (via console or gcloud)
gcloud firestore databases create --region=us-central1
```

## 2. Secrets Management

```bash
# Create secrets in Secret Manager
gcloud secrets create oauth-client-id --data-file=- <<< "your-client-id"
gcloud secrets create oauth-client-secret --data-file=- <<< "your-secret"
gcloud secrets create gemini-api-key --data-file=- <<< "your-api-key"

# Grant access to Cloud Run service account
PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding oauth-client-id \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

## 3. Environment Variables

Create production environment variables:

```bash
# Set in Cloud Run
gcloud run services update workspace-adk \
  --update-env-vars \
    ENVIRONMENT=production,\
    LOG_LEVEL=INFO,\
    USE_CLOUD_LOGGING=true,\
    SESSION_STORAGE=firestore,\
    GOOGLE_CLOUD_PROJECT=your-project-id
```

## 4. Deploy

### Using GitHub Actions (Recommended)

1. Set GitHub secrets:
   - `GCP_PROJECT_ID`: Your Google Cloud project ID
   - `GCP_SA_KEY`: Service account JSON key

2. Push to main branch:
```bash
git push origin main
```

### Manual Deployment

```bash
# Build and deploy
gcloud run deploy workspace-adk \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 3600 \
  --max-instances 10 \
  --set-env-vars ENVIRONMENT=production,USE_CLOUD_LOGGING=true
```

## 5. Monitoring Setup

### Enable Cloud Logging

```bash
# View logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=workspace-adk" \
  --limit 50 \
  --format json
```

### Create Log-based Metrics

```bash
# Error rate metric
gcloud logging metrics create adk_error_rate \
  --description="ADK error rate" \
  --log-filter='resource.type="cloud_run_revision" AND severity>=ERROR'
```

### Setup Alerting

```bash
# Create alerting policy for high error rate
gcloud alpha monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="ADK High Error Rate" \
  --condition-display-name="Error rate > 5%" \
  --condition-threshold-value=5 \
  --condition-threshold-duration=300s
```

## 6. Testing Production Deployment

```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe workspace-adk \
  --platform managed \
  --region us-central1 \
  --format 'value(status.url)')

# Test endpoint
curl $SERVICE_URL/health
```

## 7. Continuous Monitoring

### Key Metrics to Monitor

1. **Request Latency**
   - p50, p95, p99 response times
   - Alert if p95 > 5 seconds

2. **Error Rate**
   - Track 4xx and 5xx errors
   - Alert if > 5% error rate

3. **Agent Performance**
   - Tool call success rate
   - Agent routing accuracy
   - Token usage

4. **Database Performance**
   - Query latency
   - Connection pool usage
   - Session creation/retrieval times

### Dashboards

Create custom dashboard in Cloud Console:
- Request rate and latency
- Error rate by agent
- Tool call distribution
- Database metrics

## 8. Backup and Recovery

### Database Backups

```bash
# PostgreSQL automated backups (already enabled by default)
gcloud sql backups list --instance=workspace-adk-db

# Firestore automated backups
gcloud firestore backups schedules create \
  --database='(default)' \
  --recurrence=daily \
  --retention=7d
```

### Disaster Recovery

1. **Service Rollback**
```bash
# Rollback to previous revision
gcloud run services update-traffic workspace-adk \
  --to-revisions=PREVIOUS_REVISION=100
```

2. **Database Restore**
```bash
# PostgreSQL restore
gcloud sql backups restore BACKUP_ID \
  --backup-instance=workspace-adk-db
```

## 9. Scaling Configuration

```bash
# Update scaling settings
gcloud run services update workspace-adk \
  --min-instances=1 \
  --max-instances=20 \
  --concurrency=80
```

## 10. Cost Optimization

- Use Cloud Run min-instances=0 for development
- Use Firestore for lower costs vs Cloud SQL
- Enable request timeout (3600s max)
- Monitor token usage and optimize prompts
- Use Flash models where possible (already implemented)

## Security Checklist

- [ ] Service Account has minimal required permissions
- [ ] Secrets stored in Secret Manager (not env vars)
- [ ] Cloud Run service authentication configured
- [ ] VPC connector for private database access
- [ ] Regular security audits enabled
- [ ] Audit logs enabled for all services

## Troubleshooting

### Service Won't Start

```bash
# Check logs
gcloud logging read "resource.type=cloud_run_revision" --limit 50

# Check build logs
gcloud builds list --limit=5
```

### Database Connection Issues

```bash
# Test connection from Cloud Shell
gcloud sql connect workspace-adk-db --user=postgres

# Check Cloud SQL proxy settings
```

### High Latency

- Check agent routing logic
- Review tool call performance
- Optimize database queries
- Increase Cloud Run resources

