# 🚀 Monitoring Quick Start Guide
**Google Cloud Monitoring za ADK Agent System**
**Implementirano:** 2025-11-28
**Status:** ✅ Ready to Deploy (Opcija C)

---

## 📋 ŠTO JE IMPLEMENTIRANO

### ✅ Structured JSON Logging
- **Gdje:** `monitoring/logging_config.py`, `agents/base_agent.py`
- **Što radi:**
  - Svi logovi structured sa context-om (session_id, agent_name, duration)
  - Auto-integracija sa Google Cloud Logging
  - Event types za filtriranje (agent_request_start, tool_execution_success, etc.)

### ✅ Cloud Logging Integration
- **Config:** `.env` - `USE_CLOUD_LOGGING=true`
- **Što radi:**
  - Automatski šalje sve logove u Cloud Logging
  - Visibility u Cloud Console
  - Retention: 30 dana (besplatno)

### ✅ Dashboard Configuration
- **Script:** `scripts/setup_monitoring_dashboard.py`
- **Što radi:**
  - Kreira dashboard sa 5 widgets:
    - Agent success rate
    - Request latency
    - Error rate
    - Tool execution count
    - Vertex AI API calls

### ✅ Alerts Setup
- **Script:** `scripts/setup_monitoring_alerts.py`
- **Što radi:**
  - Alert za high error rate (> 5 errors/min)
  - Alert za high latency (> 30s)
  - Auto-closes nakon 30 min

---

## 🏃 QUICK START (5 minuta)

### Step 1: Install Dependencies
```bash
# Install Google Cloud Logging package
pip install google-cloud-logging google-cloud-monitoring
```

### Step 2: Verify Configuration
```bash
# Check .env file
cat .env | grep "USE_CLOUD_LOGGING"
# Should show: USE_CLOUD_LOGGING=true
```

### Step 3: Test Cloud Logging
```bash
# Run a simple test to verify logging works
python -c "
from monitoring.logging_config import setup_logging
import logging

cloud_enabled = setup_logging(
    level='INFO',
    use_cloud_logging=True,
    project_id='$(grep GOOGLE_CLOUD_PROJECT .env | cut -d= -f2)'
)

logger = logging.getLogger('test')
logger.info('Test message', extra={'session_id': 'test-123', 'agent_name': 'test-agent'})

if cloud_enabled:
    print('✅ Cloud Logging is ACTIVE')
else:
    print('⚠️ Cloud Logging NOT active')
"
```

### Step 4: Create Dashboard (Optional)
```bash
# Create monitoring dashboard in Cloud Console
python scripts/setup_monitoring_dashboard.py
```

### Step 5: Setup Alerts (Optional)
```bash
# Create alert policies
python scripts/setup_monitoring_alerts.py
```

---

## 📊 HOW TO USE

### Viewing Logs in Cloud Console

1. **Open Cloud Logging:**
   ```
   https://console.cloud.google.com/logs?project=YOUR_PROJECT_ID
   ```

2. **Filter by session:**
   ```
   jsonPayload.session_id="session-abc123"
   ```

3. **Filter by agent:**
   ```
   jsonPayload.agent_name="researcher"
   ```

4. **Filter by event type:**
   ```
   jsonPayload.event_type="agent_request_success"
   ```

5. **Find errors only:**
   ```
   severity="ERROR"
   ```

6. **Combine filters:**
   ```
   jsonPayload.agent_name="researcher" AND jsonPayload.event_type="tool_execution_error"
   ```

### Useful Log Queries

**All agent requests from last hour:**
```
logName="projects/YOUR_PROJECT/logs/adk-agent-system"
timestamp>="2025-11-28T10:00:00Z"
jsonPayload.event_type="agent_request_start"
```

**Slow requests (> 20s):**
```
jsonPayload.event_type="agent_request_success"
jsonPayload.duration_seconds>20
```

**Failed tool executions:**
```
jsonPayload.event_type="tool_execution_error"
```

---

## 🎯 EVENT TYPES

Svi logovi imaju `event_type` za lako filtriranje:

| Event Type | Znači | Severity |
|------------|-------|----------|
| `agent_request_start` | Agent je primio request | INFO |
| `agent_request_success` | Request uspješno dovršen | INFO |
| `agent_request_error` | Request failed | ERROR |
| `agent_max_iterations` | Previše iteracija | WARNING |
| `tool_execution_start` | Tool se izvršava | INFO |
| `tool_execution_success` | Tool uspješan | INFO |
| `tool_execution_error` | Tool failed | ERROR |
| `agent_config_error` | Config problem | ERROR |

---

## 📈 LOG STRUCTURE

Svaki log sadrži:

**Base Fields (uvijek prisutni):**
- `timestamp` - ISO 8601 format
- `severity` - INFO, WARNING, ERROR
- `message` - Human-readable poruka
- `logger` - Logger name
- `session_id` - Unique session ID
- `agent_name` - Koji agent
- `agent_model` - Koji model (gemini-1.5-flash/pro)

**Request-specific Fields:**
- `duration_ms` - Trajanje u milisekundama
- `duration_seconds` - Trajanje u sekundama
- `tool_calls_count` - Broj tool poziva
- `response_length` - Veličina odgovora
- `event_type` - Tip eventa

**Tool-specific Fields:**
- `tool_name` - Naziv tool-a
- `tool_args` - Argumenti (start event)
- `result_preview` - Preview rezultata (success)
- `error` - Error message (failure)
- `error_type` - Exception type (failure)

---

## 🔗 QUICK ACCESS LINKS

Za tvoj projekt (`lyrical-star-497817-m3`):

### Logging
- **Logs Explorer:** https://console.cloud.google.com/logs?project=lyrical-star-497817-m3
- **Log Analytics:** https://console.cloud.google.com/logs/analytics?project=lyrical-star-497817-m3

### Monitoring
- **Dashboards:** https://console.cloud.google.com/monitoring/dashboards?project=lyrical-star-497817-m3
- **Metrics Explorer:** https://console.cloud.google.com/monitoring/metrics-explorer?project=lyrical-star-497817-m3
- **Alerts:** https://console.cloud.google.com/monitoring/alerting?project=lyrical-star-497817-m3

### Vertex AI
- **Dashboard:** https://console.cloud.google.com/vertex-ai?project=lyrical-star-497817-m3
- **Generative AI:** https://console.cloud.google.com/vertex-ai/generative?project=lyrical-star-497817-m3

---

## 🧪 TESTING MONITORING

### Test 1: Run a simple request
```bash
# Start the system
python main.py

# In the interactive prompt, try:
> Istražite što je Google Cloud Monitoring
```

### Test 2: Check logs appear in Cloud Console
1. Go to Logs Explorer (link above)
2. Filter: `logName="projects/lyrical-star-497817-m3/logs/adk-agent-system"`
3. You should see logs for your request!

### Test 3: Check session tracking
1. In logs, find a `session_id` value
2. Filter by that session: `jsonPayload.session_id="session-XXXXX"`
3. You should see all logs for that specific request!

---

## 💰 COST ESTIMATE

**Your current usage:**
- ~735 API calls / 7 days = ~105 calls/day
- Estimated logs: ~1,000 log entries/day
- Log volume: ~5 MB/day

**Google Cloud Free Tier:**
- Logging: 50 GB/month FREE
- Monitoring: 150 MB metrics/month FREE
- Your usage: ~150 MB logs/month = **FREE** ✅

**Expected monthly cost: $0**

---

## ⚙️ CONFIGURATION OPTIONS

### Enable/Disable Cloud Logging
```bash
# .env file
USE_CLOUD_LOGGING=true   # Enable
USE_CLOUD_LOGGING=false  # Disable (local logging only)
```

### Change Log Level
```bash
# .env file
LOG_LEVEL=DEBUG   # Very verbose
LOG_LEVEL=INFO    # Normal (recommended)
LOG_LEVEL=WARNING # Only warnings/errors
LOG_LEVEL=ERROR   # Only errors
```

### Enable JSON stdout (útil za log aggregators)
```bash
# .env file
LOG_FORMAT=json
```

---

## 🐛 TROUBLESHOOTING

### Problem: "google-cloud-logging not installed"
```bash
pip install google-cloud-logging
```

### Problem: "Permission denied"
```bash
# Check service account has permissions
gcloud projects get-iam-policy YOUR_PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:*"

# Service account needs:
# - roles/logging.logWriter
# - roles/monitoring.metricWriter
```

### Problem: "Logs not appearing in Cloud Console"
```bash
# Verify Cloud Logging is enabled
python -c "import os; from monitoring.logging_config import setup_logging; setup_logging(use_cloud_logging=True, project_id=os.getenv('GOOGLE_CLOUD_PROJECT'))"

# Check if logs are being sent
# Run a test request and check console output
```

### Problem: "Dashboard/Alert creation failed"
```bash
# Install monitoring package
pip install google-cloud-monitoring

# Check permissions
gcloud projects get-iam-policy YOUR_PROJECT_ID | grep monitoring

# Service account needs:
# - roles/monitoring.editor
```

---

## 📚 USEFUL EXAMPLES

### Example 1: Debug slow request
```bash
# 1. Find slow request in logs
jsonPayload.duration_seconds>20
jsonPayload.event_type="agent_request_success"

# 2. Get session_id from that log
# 3. View all logs for that session
jsonPayload.session_id="session-abc123"

# 4. Look for tool_execution logs to see which tool was slow
jsonPayload.event_type="tool_execution_success"
jsonPayload.session_id="session-abc123"
```

### Example 2: Track error patterns
```bash
# Find all errors
severity="ERROR"

# Group by agent
jsonPayload.agent_name="researcher"
severity="ERROR"

# Group by error type
jsonPayload.error_type="TimeoutError"
```

### Example 3: Monitor API usage
```bash
# Count requests per agent (last 24h)
logName="projects/YOUR_PROJECT/logs/adk-agent-system"
jsonPayload.event_type="agent_request_start"
timestamp>="2025-11-27T00:00:00Z"
```

---

## 🎓 NEXT STEPS (Optional)

### Phase 2 Enhancements (if needed):

1. **Custom Metrics:**
   - Create metrics from logs
   - Track business KPIs
   - Cost per request

2. **Advanced Dashboards:**
   - Multiple views (performance, cost, usage)
   - SLO tracking
   - User behavior analytics

3. **Notification Channels:**
   - Email alerts
   - Slack integration
   - PagerDuty for critical issues

4. **Request Tracing:**
   - Cloud Trace integration
   - End-to-end request tracking
   - Latency breakdown

5. **Log-based Alerts:**
   - Alert on specific error patterns
   - Anomaly detection
   - Budget alerts

---

## ✅ VERIFICATION CHECKLIST

- [ ] `google-cloud-logging` package installed
- [ ] `.env` has `USE_CLOUD_LOGGING=true`
- [ ] Service account has logging permissions
- [ ] Can see logs in Cloud Console
- [ ] Logs have `session_id` and `agent_name`
- [ ] Dashboard created (optional)
- [ ] Alerts configured (optional)

---

## 🎉 CONGRATULATIONS!

You now have:
- ✅ Structured logging with context
- ✅ Cloud Logging integration
- ✅ Dashboard ready to deploy
- ✅ Alerts ready to deploy
- ✅ Session tracking
- ✅ $0/month cost (within free tier)

**Total implementation time: ~4 hours**
**Ongoing maintenance: Minimal**
**Value: HUGE! 🚀**

---

**Questions?** Check:
- Cloud Logging docs: https://cloud.google.com/logging/docs
- Cloud Monitoring docs: https://cloud.google.com/monitoring/docs
- Your project console: https://console.cloud.google.com/?project=lyrical-star-497817-m3
