# 📊 Dashboard Setup Guide
**ADK Agent System Monitoring**

---

## 🚀 QUICK START (5 min)

### Option 1: Import Simple Dashboard (RECOMMENDED)

**Koristi:** `adk_monitoring_dashboard_simple.json` - Samo Vertex AI metrics

1. **Otvori:** https://console.cloud.google.com/monitoring/dashboards?project=lyrical-star-497817-m3

2. **Klikni:** "Create Dashboard"

3. **Switch to JSON tab** (gore desno)

4. **Kopiraj** sve iz: `dashboards/adk_monitoring_dashboard_simple.json`

5. **Paste** u JSON editor

6. **Klikni** "Save"

**Što ćeš dobiti:**
- ✅ Vertex AI Request Volume
- ✅ Latency (p50 i p99)
- ✅ Error Count

---

## 📈 ADD LOG-BASED WIDGETS (Manual - 10 min)

Za agent-specific metrics (success rate, tool executions), trebaju log-based metrics.

### Step 1: Create Log-Based Metrics

#### Metric 1: Agent Success Rate

1. **Go to:** https://console.cloud.google.com/logs/metrics?project=lyrical-star-497817-m3

2. **Klikni:** "CREATE METRIC"

3. **Metric Type:** Counter

4. **Log-based metric details:**
   - **Metric name:** `adk_agent_success_count`
   - **Description:** "Count of successful agent requests"

5. **Build filter:**
   ```
   resource.type="global"
   logName="projects/lyrical-star-497817-m3/logs/adk-agent-system"
   jsonPayload.event_type="agent_request_success"
   ```

6. **Labels (optional):**
   - Field name: `agent_name`
   - Label: `agent_name`
   - Extraction regex: `.*`
   - Value path: `jsonPayload.agent_name`

7. **Klikni** "CREATE METRIC"

---

#### Metric 2: Agent Errors

1. **CREATE METRIC** opet

2. **Details:**
   - **Name:** `adk_agent_error_count`
   - **Description:** "Count of agent errors"

3. **Filter:**
   ```
   resource.type="global"
   logName="projects/lyrical-star-497817-m3/logs/adk-agent-system"
   jsonPayload.event_type="agent_request_error"
   ```

4. **Labels:**
   - `agent_name` from `jsonPayload.agent_name`

5. **CREATE METRIC**

---

#### Metric 3: Tool Executions

1. **CREATE METRIC**

2. **Details:**
   - **Name:** `adk_tool_execution_count`
   - **Description:** "Count of tool executions"

3. **Filter:**
   ```
   resource.type="global"
   logName="projects/lyrical-star-497817-m3/logs/adk-agent-system"
   jsonPayload.event_type="tool_execution_success"
   ```

4. **Labels:**
   - `tool_name` from `jsonPayload.tool_name`
   - `agent_name` from `jsonPayload.agent_name`

5. **CREATE METRIC**

---

#### Metric 4: Request Latency (Distribution)

1. **CREATE METRIC**

2. **Metric Type:** **Distribution**

3. **Details:**
   - **Name:** `adk_request_latency`
   - **Description:** "Agent request latency distribution"

4. **Filter:**
   ```
   resource.type="global"
   logName="projects/lyrical-star-497817-m3/logs/adk-agent-system"
   jsonPayload.event_type="agent_request_success"
   ```

5. **Field name:** `jsonPayload.duration_ms`

6. **Labels:**
   - `agent_name` from `jsonPayload.agent_name`

7. **CREATE METRIC**

---

### Step 2: Add Widgets to Dashboard

Nakon što su metrics kreirani (čeka se 1-2 minute da se pojave):

1. **Otvori dashboard** što si kreirao

2. **Klikni** "Add Widget" → "Line Chart"

3. **Select Metric:**
   - Resource type: "Global"
   - Metric: `logging.googleapis.com/user/adk_agent_success_count`

4. **Configure:**
   - Aggregation: Rate (per minute)
   - Group by: `agent_name`

5. **Klikni** "Apply"

6. **Repeat** za ostale metrics

---

## 🎨 RECOMMENDED DASHBOARD LAYOUT

**Row 1 (Top):**
- Vertex AI Request Volume (full width)

**Row 2:**
- Agent Success Rate (left) | Agent Error Rate (right)

**Row 3:**
- Request Latency p50 (left) | Request Latency p99 (right)

**Row 4:**
- Tool Executions by type (full width, stacked area)

**Row 5:**
- Vertex AI Error Count (full width)

---

## 🔧 WIDGET CONFIGURATIONS

### Agent Success Rate Widget

```
Resource: Global
Metric: logging.googleapis.com/user/adk_agent_success_count
Filter: None
Aggregation:
  - Aligner: rate (1 minute)
  - Reducer: sum
  - Group by: agent_name
Chart type: Line
```

### Agent Error Rate Widget

```
Resource: Global
Metric: logging.googleapis.com/user/adk_agent_error_count
Aggregation:
  - Aligner: rate (1 minute)
  - Reducer: sum
  - Group by: agent_name
Chart type: Line
Color: Red
```

### Request Latency Widget

```
Resource: Global
Metric: logging.googleapis.com/user/adk_request_latency
Aggregation:
  - Aligner: delta (1 minute)
  - Reducer: percentile_50 (or percentile_99)
  - Group by: agent_name
Chart type: Line
Y-axis: Milliseconds
```

### Tool Executions Widget

```
Resource: Global
Metric: logging.googleapis.com/user/adk_tool_execution_count
Aggregation:
  - Aligner: rate (1 minute)
  - Reducer: sum
  - Group by: tool_name
Chart type: Stacked Area
```

---

## 💡 TIPS

### 1. Wait for Data
- Log-based metrics need data points
- Run a few test requests first
- Wait 2-3 minutes for metrics to appear

### 2. Test Filters
- Use Logs Explorer to test filters first
- Copy working filters to metric definitions

### 3. Time Range
- Set dashboard to "Last 1 hour" for testing
- Change to "Last 6 hours" or "Last 1 day" for monitoring

### 4. Auto-refresh
- Enable auto-refresh (1 minute interval)
- Good for live monitoring

### 5. Save & Share
- Save dashboard after each change
- Share link with team
- Can export as JSON

---

## 🐛 TROUBLESHOOTING

### "No data available"
**Causes:**
1. Metrics just created (wait 2-3 minutes)
2. No log entries yet (run test request)
3. Filter doesn't match logs

**Fix:**
- Run: `python test_monitoring.py`
- Wait 2 minutes
- Refresh dashboard

### "Metric not found"
**Causes:**
1. Metric not created yet
2. Wrong metric path

**Fix:**
- Check: https://console.cloud.google.com/logs/metrics?project=lyrical-star-497817-m3
- Verify metric exists
- Copy exact metric path

### Widget shows error
**Causes:**
1. Invalid aggregation
2. Wrong resource type

**Fix:**
- Resource must be "Global"
- Use rate/delta for counters
- Use percentile for distributions

---

## 📚 ALTERNATIVE: Manual Widget Creation

Ako ne želiš JSON import:

1. **Go to:** https://console.cloud.google.com/monitoring/dashboards?project=lyrical-star-497817-m3

2. **Create Dashboard**

3. **Add Widget** → Type: Line Chart

4. **For each widget:**
   - Click "Select a metric"
   - Search for metric name
   - Configure aggregation
   - Set display options
   - Click Apply

5. **Arrange widgets:**
   - Drag to reposition
   - Resize as needed

6. **Save dashboard**

---

## 🔗 USEFUL LINKS

**Your Project:**
- **Dashboards:** https://console.cloud.google.com/monitoring/dashboards?project=lyrical-star-497817-m3
- **Metrics:** https://console.cloud.google.com/logs/metrics?project=lyrical-star-497817-m3
- **Logs Explorer:** https://console.cloud.google.com/logs?project=lyrical-star-497817-m3

**Documentation:**
- [Cloud Monitoring Dashboards](https://cloud.google.com/monitoring/dashboards)
- [Log-based Metrics](https://cloud.google.com/logging/docs/logs-based-metrics)
- [MQL Reference](https://cloud.google.com/monitoring/mql)

---

## ✅ VERIFICATION

After setup, verify:

- [ ] Simple dashboard imported successfully
- [ ] Vertex AI metrics showing data
- [ ] Log-based metrics created (4 metrics)
- [ ] Metrics showing in Metrics Explorer
- [ ] Widgets added to dashboard
- [ ] Dashboard displays data (not "No data")
- [ ] Auto-refresh enabled
- [ ] Dashboard saved

---

## 🎯 NEXT STEPS

1. **Import simple dashboard** (START HERE!)
2. **Run test requests** to generate data
3. **Create log-based metrics** (optional)
4. **Add custom widgets** (optional)
5. **Setup alerts** (see separate guide)

---

**Status:** Ready to deploy
**Complexity:** Simple dashboard (5 min) | Full dashboard (20 min)
**Maintenance:** None
