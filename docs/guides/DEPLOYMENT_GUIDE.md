# 🚀 DEPLOYMENT & USAGE GUIDE

**Google Workspace ADK Multi-Agent System**
**Version:** 1.0.0
**Date:** 2025-11-27
**Status:** Production Ready ✅

---

## 📋 TABLE OF CONTENTS

1. [System Requirements](#1-system-requirements)
2. [Installation](#2-installation)
3. [Configuration](#3-configuration)
4. [Running the System](#4-running-the-system)
5. [Using the Agents](#5-using-the-agents)
6. [Testing](#6-testing)
7. [Monitoring](#7-monitoring)
8. [Troubleshooting](#8-troubleshooting)
9. [Production Deployment](#9-production-deployment)

---

## 1. SYSTEM REQUIREMENTS

### Minimum Requirements

- **OS:** Windows 10/11, macOS 10.15+, Linux (Ubuntu 20.04+)
- **Python:** 3.10 or higher
- **RAM:** 4 GB minimum, 8 GB recommended
- **Storage:** 1 GB free space
- **Internet:** Stable connection for API calls

### Required Accounts

- **Google Cloud Project** with Vertex AI API enabled
- **Google Workspace Account** (for OAuth2)
- **Google API Credentials:**
  - OAuth 2.0 Client ID & Secret
  - OR Service Account credentials

---

## 2. INSTALLATION

### Step 1: Clone Repository

```bash
git clone <repository-url>
cd google_claude
```

### Step 2: Create Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

**Key Dependencies:**
- `google-genai` - Google AI Python SDK
- `google-auth` - Google authentication
- `google-api-python-client` - Google Workspace APIs
- `python-dotenv` - Environment variable management

---

## 3. CONFIGURATION

### Step 1: Environment Variables

Create `.env` file in project root:

```bash
# Google Cloud Configuration
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_API_KEY=your-api-key

# OAuth 2.0 Credentials (for user access)
GOOGLE_OAUTH_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
GOOGLE_OAUTH_REFRESH_TOKEN=your-refresh-token

# Service Account (optional, for service access)
GOOGLE_SERVICE_ACCOUNT_FILE=path/to/service-account.json

# Logging
LOG_LEVEL=INFO
USE_CLOUD_LOGGING=false

# Environment
ENVIRONMENT=development
```

### Step 2: Google Cloud Setup

#### 2a. Enable APIs

Enable these APIs in Google Cloud Console:

1. **Vertex AI API**
2. **Gmail API**
3. **Google Calendar API**
4. **Google Drive API**
5. **Google Docs API**
6. **Google Sheets API**
7. **People API** (Contacts)
8. **Tasks API**

```bash
# Enable via gcloud CLI
gcloud services enable aiplatform.googleapis.com
gcloud services enable gmail.googleapis.com
gcloud services enable calendar-json.googleapis.com
gcloud services enable drive.googleapis.com
gcloud services enable docs.googleapis.com
gcloud services enable sheets.googleapis.com
gcloud services enable people.googleapis.com
gcloud services enable tasks.googleapis.com
```

#### 2b. OAuth 2.0 Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **APIs & Services > Credentials**
3. Click **Create Credentials > OAuth client ID**
4. Select **Desktop app** as application type
5. Download JSON and extract:
   - `client_id`
   - `client_secret`

#### 2c. Get Refresh Token

Run authentication CLI:

```bash
python tools/oauth_cli.py --auth
```

This will:
1. Open browser for Google sign-in
2. Request necessary scopes
3. Generate refresh token
4. Save token to `.env`

### Step 3: Verify Setup

```bash
# Test environment variables
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('API Key:', os.getenv('GOOGLE_API_KEY')[:10] + '...')"

# Test Vertex AI access
python test_available_models.py
```

Expected output:
```
✓ Vertex AI configured
✓ gemini-2.0-flash-exp available
✓ OAuth2 credentials loaded
```

---

## 4. RUNNING THE SYSTEM

### Interactive Mode (Recommended)

```bash
python main.py
```

This starts the interactive CLI:

```
=== Google Workspace ADK Multi-Agent System ===
Environment: development

=== Starting Interactive Mode ===
Type 'exit' or 'quit' to stop
Type 'help' for available commands

You: _
```

### Available Commands

```
help      - Show help message
agents    - List all available agents
status    - Show system status
exit/quit - Exit the system
```

### Example Usage

```
You: Show me my last 5 emails

🤖 Processing...

Orchestrator routing: 'Show me my last 5 emails' -> mailer
Reasoning: Email keywords detected

Delegating to mailer agent...

✅ Result:
Here are your last 5 emails:

1. From: Google One <googleone-noreply@google.com>
   Subject: Povećajte produktivnost uz Gemini...
   Date: Nov 25, 2025

2. From: GitHub <noreply@github.com>
   Subject: Your weekly repository updates
   Date: Nov 24, 2025

[...]
```

---

## 5. USING THE AGENTS

### Available Agents

| Agent | Specialty | Example Queries |
|-------|-----------|-----------------|
| **mailer** | Gmail operations | "Show my unread emails"<br>"Send email to john@example.com"<br>"Search emails from last week" |
| **secretary** | Calendar | "What events do I have today?"<br>"Show my schedule for next week"<br>"Create meeting tomorrow at 2pm" |
| **librarian** | Google Drive | "Find my budget spreadsheet"<br>"Show recent files"<br>"Find PDFs from last month" |
| **scribe** | Google Docs | "Create a new document"<br>"Show my recent docs"<br>"Format this text as a doc" |
| **analyst** | Google Sheets | "Show my spreadsheets"<br>"Read data from Budget sheet"<br>"Update cell A1" |
| **rolodex** | Contacts | "Show my contacts"<br>"Find contact for john@example.com"<br>"List all contacts" |
| **tracker** | Tasks | "Show my tasks"<br>"Create new task"<br>"Mark task as complete" |
| **researcher** | Web research | "Research topic X"<br>"Find information about Y" |
| **scraper** | Web scraping | "Extract data from URL"<br>"Scrape webpage" |

### Query Patterns

#### Simple Queries
```
"Show me my emails"
"What's on my calendar today?"
"List my Drive files"
```

#### Complex Queries
```
"Find all unread emails from last week and summarize them"
"Show me emails from Google that have attachments"
"Find all documents modified in the last month"
```

#### Multi-Agent Queries
```
"Check my emails for meeting invites and show me today's calendar"
"Find recent PDFs in Drive and check if I received any via email"
"Show me my tasks and calendar for today"
```

### Natural Language Tips

✅ **Good Queries:**
- "Show my last 5 emails"
- "What events do I have this week?"
- "Find files modified in the last month"

❌ **Avoid:**
- Too vague: "Do something"
- Too technical: "Call gmail.users().messages().list()"
- Multiple unrelated tasks: "Email + weather + news"

---

## 6. TESTING

### Quick Smoke Test (1 minute)

```bash
python tests/test_comprehensive_real_api.py --mode quick
```

Runs 10 basic tests covering all core agents.

### Full Test Suite (3 minutes)

```bash
python tests/test_comprehensive_real_api.py --mode full
```

Runs 31 comprehensive tests:
- Simple queries
- Complex queries
- Multi-agent collaboration
- Edge cases
- Performance & caching
- Routing intelligence

### Custom Single Test

```bash
python tests/test_comprehensive_real_api.py --mode custom --query "Show me my emails"
```

### Expected Results

```
Total Tests: 31
✅ Passed: 31
❌ Failed: 0
⏭️  Skipped: 0

📊 Success Rate: 100.0%
```

---

## 7. MONITORING

### View Real-Time Metrics

```bash
python scripts/show_metrics.py --watch
```

Shows:
- Agent call counts (success/failure)
- Tool execution stats
- Response times
- Cache hit rates
- Error counts

### Check Logs

Logs are written to console and optionally to files:

```bash
# View recent logs
tail -f logs/agent.log

# Search for errors
grep ERROR logs/agent.log

# View specific agent logs
grep "agent.mailer" logs/agent.log
```

### Metrics Summary

```python
from monitoring.metrics import get_metrics_collector

metrics = get_metrics_collector()
summary = metrics.get_summary()

print(f"Agent Calls: {summary['counters']}")
print(f"Tool Calls: {summary['counters']}")
print(f"Cache Stats: {summary['cache']}")
```

---

## 8. TROUBLESHOOTING

### Common Issues

#### Issue: "404 NOT_FOUND - Model not found"

**Cause:** Wrong model name or region

**Solution:**
```bash
# Check available models
python test_available_models.py

# Update model in agent_registry.py
model="gemini-2.0-flash-exp"
```

#### Issue: "401 UNAUTHORIZED"

**Cause:** Invalid or expired credentials

**Solution:**
```bash
# Re-authenticate
python tools/oauth_cli.py --auth

# Verify credentials loaded
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('GOOGLE_OAUTH_REFRESH_TOKEN'))"
```

#### Issue: "429 RESOURCE_EXHAUSTED - Quota exceeded"

**Cause:** API rate limit hit

**Solution:**
- Wait for quota reset (usually 1 minute)
- Check quota in Google Cloud Console
- Request quota increase if needed

#### Issue: Tools fail with "Tool not found"

**Cause:** Tool registry not initialized

**Solution:**
```python
from tools.initialize_tools import ensure_tools_initialized
ensure_tools_initialized()
```

#### Issue: Unicode errors in console

**Cause:** Windows console encoding

**Solution:**
```bash
# Set UTF-8 encoding
chcp 65001

# Or run without emojis
# (emojis are cosmetic, don't affect functionality)
```

### Debug Mode

Enable detailed logging:

```bash
# In .env
LOG_LEVEL=DEBUG

# Or temporarily
LOG_LEVEL=DEBUG python main.py
```

### Reset Everything

```bash
# Clear cache
rm -rf __pycache__
rm -rf */__pycache__

# Reinstall dependencies
pip install --upgrade -r requirements.txt

# Re-authenticate
python tools/oauth_cli.py --auth
```

---

## 9. PRODUCTION DEPLOYMENT

### Deployment Options

#### Option 1: Local Server

```bash
# Run as background service
nohup python main.py &

# Or use screen/tmux
screen -S google-adk
python main.py
# Ctrl+A, D to detach
```

#### Option 2: Docker Container

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

Build and run:

```bash
docker build -t google-adk .
docker run -d --name google-adk \
  --env-file .env \
  google-adk
```

#### Option 3: Cloud Run / Kubernetes

```yaml
# kubernetes-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: google-adk
spec:
  replicas: 2
  selector:
    matchLabels:
      app: google-adk
  template:
    metadata:
      labels:
        app: google-adk
    spec:
      containers:
      - name: google-adk
        image: gcr.io/your-project/google-adk:latest
        env:
        - name: GOOGLE_CLOUD_PROJECT
          value: "your-project-id"
        # ... other env vars
```

### Production Checklist

- [ ] Environment variables secured (use Secret Manager)
- [ ] Logging configured (Cloud Logging)
- [ ] Monitoring dashboards set up
- [ ] Alerting configured
- [ ] Rate limiting tested
- [ ] Load testing completed
- [ ] Backup strategy defined
- [ ] Disaster recovery plan
- [ ] Documentation updated
- [ ] User training completed

### Security Best Practices

1. **Never commit `.env` to git**
   ```bash
   # Add to .gitignore
   echo ".env" >> .gitignore
   ```

2. **Use Secret Manager in production**
   ```python
   from google.cloud import secretmanager

   def get_secret(secret_id):
       client = secretmanager.SecretManagerServiceClient()
       name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
       response = client.access_secret_version(request={"name": name})
       return response.payload.data.decode("UTF-8")
   ```

3. **Rotate credentials regularly**
   - OAuth tokens: Every 90 days
   - Service account keys: Every 180 days

4. **Monitor API usage**
   - Set up quota alerts
   - Track unusual patterns
   - Log all API calls

### Performance Optimization

1. **Enable caching**
   ```python
   # Already enabled, tune TTL
   cache_ttl = 300  # 5 minutes
   ```

2. **Use connection pooling**
   ```python
   # Already implemented in API client
   ```

3. **Optimize LLM calls**
   ```python
   # Use lower temperature for routing
   temperature = 0.2

   # Cache LLM responses
   # Already implemented
   ```

4. **Horizontal scaling**
   - Run multiple instances
   - Use load balancer
   - Share cache (Redis)

---

## 📚 APPENDIX

### Useful Commands Reference

```bash
# Start system
python main.py

# Run tests
python tests/test_comprehensive_real_api.py --mode full

# View metrics
python scripts/show_metrics.py --watch

# Re-authenticate
python tools/oauth_cli.py --auth

# Check available models
python test_available_models.py

# View logs
tail -f logs/agent.log

# Clear cache
rm -rf __pycache__
```

### Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| GOOGLE_CLOUD_PROJECT | Yes | - | GCP project ID |
| GOOGLE_CLOUD_LOCATION | No | us-central1 | Vertex AI region |
| GOOGLE_API_KEY | Yes* | - | Google AI API key |
| GOOGLE_OAUTH_CLIENT_ID | Yes* | - | OAuth client ID |
| GOOGLE_OAUTH_CLIENT_SECRET | Yes* | - | OAuth secret |
| GOOGLE_OAUTH_REFRESH_TOKEN | Yes* | - | Refresh token |
| GOOGLE_SERVICE_ACCOUNT_FILE | No | - | Service account JSON |
| LOG_LEVEL | No | INFO | Logging level |
| USE_CLOUD_LOGGING | No | false | Use Cloud Logging |
| ENVIRONMENT | No | development | Environment name |

*Either API key OR OAuth credentials required

### File Structure

```
google_claude/
├── agents/              # Agent implementations
│   ├── base_agent.py
│   ├── orchestrator/
│   ├── mailer/
│   ├── secretary/
│   └── ...
├── config/              # Configuration
│   ├── agent_registry.py
│   └── auth_config.py
├── tools/               # Tools & APIs
│   ├── mcp_toolsets/
│   ├── custom_tools/
│   ├── api_implementations/
│   └── tool_registry.py
├── monitoring/          # Monitoring
│   ├── logging_config.py
│   └── metrics.py
├── tests/              # Tests
│   └── test_comprehensive_real_api.py
├── scripts/            # Utility scripts
│   └── show_metrics.py
├── main.py            # Entry point
├── requirements.txt   # Dependencies
└── .env              # Configuration (not in git)
```

### Support & Resources

- **Documentation:** `DETALJN A_ANALIZA_SUSTAVA.md`
- **Test Report:** `FINAL_TEST_REPORT_2025-11-27.md`
- **Fixes Log:** `FIXES_APPLIED_2025-11-27.md`
- **ADK Docs:** https://google.github.io/adk-docs/

---

**Last Updated:** 2025-11-27
**Version:** 1.0.0
**Status:** ✅ Production Ready

---

**🚀 Happy Deploying! 🚀**
