# Smart Orchestrator - Workflow Examples

Comprehensive guide to Smart Orchestrator behavior with real-world workflow examples.

## Table of Contents

1. [Orchestrator Architecture](#orchestrator-architecture)
2. [Single-Step Workflows](#single-step-workflows)
3. [Multi-Step Workflows](#multi-step-workflows)
4. [Complex Workflows with Dependencies](#complex-workflows-with-dependencies)
5. [Error Handling Workflows](#error-handling-workflows)
6. [Parallel vs Sequential Execution](#parallel-vs-sequential-execution)
7. [Common Patterns](#common-patterns)
8. [Anti-Patterns](#anti-patterns)

---

## Orchestrator Architecture

### How Smart Orchestrator Works

```
User Query
    ↓
Smart Orchestrator (LlmAgent)
    ├─ Phase 1: Understand Intent
    ├─ Phase 2: Plan Agent Sequence
    ├─ Phase 3: Execute ONE BY ONE
    │    ├→ Call agent_tool_1() → wait → extract result
    │    ├→ Call agent_tool_2() → wait → extract result
    │    └→ Call agent_tool_3() → wait → extract result
    └─ Phase 4: Synthesize & Return
```

### Key Principles

1. **Sequential Execution** - Agents called ONE BY ONE, never simultaneously (unless explicitly desired)
2. **Explicit Result Passing** - Orchestrator extracts information and passes to next agent
3. **Context Awareness** - Each agent receives relevant context from previous steps
4. **Verification** - Orchestrator verifies success before proceeding
5. **Error Recovery** - Orchestrator handles failures gracefully

---

## Single-Step Workflows

### Example 1: Simple Research

**User Query:**
```
"What is Google Agent Development Kit?"
```

**Orchestrator Execution:**

```
PHASE 1: Understand Intent
  - Single task: Research query
  - Agent needed: Researcher
  - No multi-step workflow

PHASE 2: Plan
  - Step 1: Call researcher with query
  - No additional steps needed

PHASE 3: Execute
  STEP 1: Call researcher
    Tool: researcher(query="What is Google Agent Development Kit")

    [Researcher executes:]
    - Uses google_search_grounding("Google Agent Development Kit")
    - Finds documentation, articles, sources
    - Synthesizes answer
    - Returns: "Google Agent Development Kit (ADK) is a framework for building AI agents..."

    Result: Research complete with sources

PHASE 4: Synthesize
  "Google Agent Development Kit (ADK) is a framework for building AI agents using Python, TypeScript, Go, or Java. It provides:

  - LLM agents with tool integration
  - Multi-agent systems
  - Workflow agents (sequential, parallel, loop)
  - Production deployment patterns

  Sources:
  - Google ADK Documentation
  - GitHub Repository
  - Blog posts"
```

### Example 2: Email Search

**User Query:**
```
"Find emails from my boss about the quarterly review"
```

**Orchestrator Execution:**

```
PHASE 1: Understand Intent
  - Single task: Email search
  - Agent needed: Mailer
  - No additional steps

PHASE 2: Plan
  - Step 1: Call mailer to search emails

PHASE 3: Execute
  STEP 1: Call mailer
    Tool: mailer(action="search", query="from:boss@company.com subject:quarterly review")

    [Mailer executes:]
    - Searches Gmail: "from:boss@company.com subject:quarterly review"
    - Finds 2 threads
    - Reads thread content
    - Returns summary

    Result: Found 2 emails with details

PHASE 4: Synthesize
  "Found 2 emails from your boss about quarterly review:

  1. Subject: Q4 Quarterly Review - Action Items
     Date: Jan 10, 2026
     Preview: Please prepare your section by Friday...

  2. Subject: Quarterly Review Meeting
     Date: Jan 5, 2026
     Preview: Scheduled for Jan 20 at 2pm..."
```

---

## Multi-Step Workflows

### Example 3: Research → Document → Email

**User Query:**
```
"Research quantum computing, create a document, and email it to john@example.com"
```

**Orchestrator Execution:**

```
PHASE 1: Understand Intent
  - Three tasks identified:
    1. Research quantum computing
    2. Create document with research
    3. Email document to recipient
  - Agents needed: Researcher, Scribe, Mailer
  - Sequential workflow (each step depends on previous)

PHASE 2: Plan
  Step 1: researcher(query="quantum computing comprehensive research")
  Step 2: scribe(action="create", title="Quantum Computing", content=<from step 1>)
  Step 3: mailer(action="send", to="john@example.com", body="Document: <link from step 2>")

PHASE 3: Execute

  STEP 1: Call researcher
    Tool: researcher(query="quantum computing comprehensive research")

    [Researcher executes:]
    - google_search_grounding("quantum computing")
    - scrape_multiple_urls([tech articles])
    - Synthesizes comprehensive research
    - Returns: "# Quantum Computing Research
                ## Overview
                [detailed content]
                ## Applications
                [detailed content]
                ## Sources
                [list of sources]"

    Result received by orchestrator:
      research_content = "[full research text with sources]"

    ✓ Step 1 complete

  STEP 2: Call scribe
    Tool: scribe(
      action="create",
      title="Quantum Computing Research",
      content="[full research content from step 1]"
    )

    [Scribe executes:]
    - Creates Google Doc with title
    - Formats content (headings, lists)
    - Shares document publicly (CRITICAL!)
    - Returns: "Document created: https://docs.google.com/document/d/abc123xyz
                Document shared publicly for viewing."

    Result received by orchestrator:
      document_url = "https://docs.google.com/document/d/abc123xyz"
      document_title = "Quantum Computing Research"

    ✓ Step 2 complete

  STEP 3: Call mailer
    Tool: mailer(
      action="send",
      to="john@example.com",
      subject="Research Document - Quantum Computing",
      body="Hi John,

As requested, here is the research document on quantum computing:

📄 Document: Quantum Computing Research
🔗 Link: https://docs.google.com/document/d/abc123xyz

The document covers quantum computing overview, applications, and current developments.

Best regards"
    )

    [Mailer executes:]
    - Validates john@example.com (has @) ✓
    - Composes professional email
    - Sends via Gmail API
    - Returns: "Email sent successfully to john@example.com"

    Result received by orchestrator:
      email_sent = True

    ✓ Step 3 complete

PHASE 4: Synthesize
  "✅ All tasks completed successfully!

  1. ✅ Research completed on quantum computing
  2. ✅ Document created: Quantum Computing Research
  3. ✅ Email sent to john@example.com

  📄 Document Link: https://docs.google.com/document/d/abc123xyz

  John can now access the document and review the research."
```

### Example 4: Schedule Meeting → Send Confirmation

**User Query:**
```
"Schedule meeting with Sarah tomorrow at 2pm and send her confirmation"
```

**Orchestrator Execution:**

```
CONTEXT:
  Current date: 2026-01-13 (Monday)
  Tomorrow: 2026-01-14 (Tuesday)
  User timezone: Europe/Zagreb (CET)

PHASE 1: Understand Intent
  - Three tasks:
    1. Schedule calendar event
    2. Find Sarah's email
    3. Send confirmation email
  - Agents needed: Secretary, Rolodex, Mailer

PHASE 2: Plan
  Step 1: secretary(action="create_event", details for tomorrow 14:00)
  Step 2: rolodex(query="Sarah") to get email
  Step 3: mailer(send confirmation with EXPLICIT date)

PHASE 3: Execute

  STEP 1: Call secretary
    Tool: secretary(
      action="create_event",
      summary="Meeting with Sarah",
      start_time="2026-01-14T14:00:00+01:00",  # RFC3339 with timezone
      end_time="2026-01-14T15:00:00+01:00",
      timezone="Europe/Zagreb"
    )

    [Secretary executes:]
    - Checks for conflicts → none found
    - Creates calendar event
    - Returns: "Event created:
                Title: Meeting with Sarah
                Date: 2026-01-14 (Tuesday, utorak)
                Time: 14:00-15:00 CET
                Event ID: evt_abc123
                Calendar: https://calendar.google.com/event?eid=evt_abc123

                Relative reference: sutra (utorak 14. siječnja) u 14:00"

    Result received by orchestrator:
      event_created = True
      event_date_explicit = "Tuesday, January 14, 2026"
      event_date_relative = "sutra (utorak 14. siječnja)"
      event_time = "14:00 CET"
      calendar_link = "https://calendar.google.com/event?eid=evt_abc123"

    ✓ Step 1 complete

  STEP 2: Call rolodex
    Tool: rolodex(query="Sarah")

    [Rolodex executes:]
    - Searches contacts for "Sarah"
    - Finds 1 match
    - Returns: "Found contact:
                Name: Sarah Johnson
                Email: sarah.johnson@company.com
                Phone: +385-91-123-4567
                Company: Tech Corp"

    Result received by orchestrator:
      recipient_email = "sarah.johnson@company.com"
      recipient_name = "Sarah Johnson"

    ✓ Step 2 complete

  STEP 3: Call mailer
    Tool: mailer(
      action="send",
      to="sarah.johnson@company.com",
      subject="Meeting Confirmation - Tuesday, Jan 14 at 2pm",
      body="Hi Sarah,

This is to confirm our meeting scheduled for **sutra (utorak 14. siječnja)** at **14:00 CET**.

📅 Date: Tuesday, January 14, 2026
⏰ Time: 2:00 PM CET
🔗 Calendar: https://calendar.google.com/event?eid=evt_abc123

Looking forward to meeting with you!

Best regards"
    )

    [Mailer executes:]
    - Validates sarah.johnson@company.com ✓
    - Composes email with EXPLICIT date (not just "tomorrow")
    - Sends confirmation
    - Returns: "Email sent to sarah.johnson@company.com"

    Result received by orchestrator:
      confirmation_sent = True

    ✓ Step 3 complete

PHASE 4: Synthesize
  "✅ Meeting scheduled and confirmation sent!

  📅 Event: Meeting with Sarah
  📆 Date: Tomorrow (Tuesday, January 14, 2026) at 2:00 PM CET
  📧 Confirmation sent to: sarah.johnson@company.com
  🔗 Calendar: https://calendar.google.com/event?eid=evt_abc123

  Sarah has been notified with the meeting details and calendar link."
```

---

## Complex Workflows with Dependencies

### Example 5: Invoice Processing Workflow

**User Query:**
```
"Process the invoice from Supplier ABC, create expense record, schedule payment, and notify finance team"
```

**Orchestrator Execution:**

```
PHASE 1: Understand Intent
  - Four interdependent tasks:
    1. Find invoice document
    2. Create expense record
    3. Schedule payment event
    4. Notify team via email
  - Agents: Librarian, Expense, Secretary, Mailer

PHASE 2: Plan
  Step 1: librarian(search "Supplier ABC invoice")
  Step 2: expense(create record with invoice details)
  Step 3: secretary(schedule payment due date)
  Step 4: mailer(notify finance team with all links)

PHASE 3: Execute

  STEP 1: Call librarian
    Tool: librarian(query="Supplier ABC invoice", file_type="pdf")

    [Librarian executes:]
    - Searches Google Drive
    - Finds invoice PDF
    - Returns: "Found file:
                Name: Invoice_SupplierABC_202601.pdf
                ID: file_xyz789
                URL: https://drive.google.com/file/d/file_xyz789
                Amount: $5,000
                Due: 2026-01-31"

    Result:
      invoice_id = "file_xyz789"
      invoice_url = "https://drive.google.com/file/d/file_xyz789"
      invoice_amount = "$5,000"
      due_date = "2026-01-31"

    ✓ Step 1 complete

  STEP 2: Call expense
    Tool: expense(
      action="create",
      category="Vendor Payment",
      amount=5000,
      description="Supplier ABC - January invoice",
      invoice_id="file_xyz789",
      due_date="2026-01-31"
    )

    [Expense executes:]
    - Creates expense tracking entry
    - Links to invoice document
    - Returns: "Expense created:
                ID: exp_456
                Category: Vendor Payment
                Amount: $5,000
                Status: Pending approval
                Tracker URL: https://docs.google.com/spreadsheets/d/tracker123"

    Result:
      expense_id = "exp_456"
      tracker_url = "https://docs.google.com/spreadsheets/d/tracker123"

    ✓ Step 2 complete

  STEP 3: Call secretary
    Tool: secretary(
      action="create_event",
      summary="Payment Due: Supplier ABC",
      date="2026-01-31",
      all_day=True,
      description="Invoice payment due: $5,000"
    )

    [Secretary executes:]
    - Creates all-day calendar reminder
    - Returns: "Event created:
                Title: Payment Due: Supplier ABC
                Date: January 31, 2026 (All day)
                Calendar: https://calendar.google.com/event?eid=evt_pay123"

    Result:
      payment_reminder_set = True
      calendar_link = "https://calendar.google.com/event?eid=evt_pay123"

    ✓ Step 3 complete

  STEP 4: Call mailer
    Tool: mailer(
      action="send",
      to="finance@company.com",
      subject="Invoice Processed - Supplier ABC ($5,000)",
      body="Hi Finance Team,

Invoice from Supplier ABC has been processed and is ready for approval.

📄 Invoice: https://drive.google.com/file/d/file_xyz789
💰 Amount: $5,000
📅 Due Date: January 31, 2026
📊 Expense Record: https://docs.google.com/spreadsheets/d/tracker123
🔔 Payment Reminder: https://calendar.google.com/event?eid=evt_pay123

Please review and approve for payment.

Best regards"
    )

    [Mailer executes:]
    - Sends notification with all relevant links
    - Returns: "Email sent to finance@company.com"

    Result:
      team_notified = True

    ✓ Step 4 complete

PHASE 4: Synthesize
  "✅ Invoice processing complete!

  1. ✅ Invoice found and retrieved
  2. ✅ Expense record created (ID: exp_456)
  3. ✅ Payment reminder scheduled for Jan 31
  4. ✅ Finance team notified

  📄 Invoice: https://drive.google.com/file/d/file_xyz789
  📊 Expense Tracker: https://docs.google.com/spreadsheets/d/tracker123

  Finance team can now review and approve the payment."
```

---

## Error Handling Workflows

### Example 6: Workflow with Recovery

**User Query:**
```
"Research AI safety, create doc, email to team@company.com"
```

**Orchestrator Execution with Error:**

```
PHASE 3: Execute

  STEP 1: Call researcher
    Tool: researcher(query="AI safety comprehensive research")

    [Researcher executes:]
    - Attempts google_search_grounding()
    - ❌ ERROR: "API rate limit exceeded"
    - Returns: "ERROR: Search API rate limited. Unable to complete research."

    Result:
      error = "Rate limit exceeded"
      research_content = None

    ✗ Step 1 FAILED

ORCHESTRATOR THINKS:
  "Research failed due to rate limit. Options:
   1. Retry with exponential backoff (may still fail)
   2. Use alternative research method (if available)
   3. Inform user and suggest retry later

   Best approach: Inform user with specific error and suggest retry timing."

PHASE 4: Error Response
  "⚠️ Unable to complete workflow

  The research step failed due to API rate limiting on the search service. This typically resolves within 5-10 minutes.

  What happened:
  ✗ Step 1: Research - Failed (rate limit)
  ⏸ Step 2: Document creation - Not started
  ⏸ Step 3: Email - Not started

  Would you like me to:
  1. Retry the workflow in 5 minutes
  2. Create a reminder to retry later
  3. Proceed with alternative research methods (if available)

  Please let me know how you'd like to proceed."
```

### Example 7: Partial Failure with Continuation

**User Query:**
```
"Send meeting invite to John, Sarah, and Mike for tomorrow at 3pm"
```

**Orchestrator Execution:**

```
PHASE 3: Execute

  STEP 1: Find John's email
    Tool: rolodex(query="John")
    Result: john@company.com ✓

  STEP 2: Find Sarah's email
    Tool: rolodex(query="Sarah")
    Result: sarah@company.com ✓

  STEP 3: Find Mike's email
    Tool: rolodex(query="Mike")
    Result: ERROR - "Multiple Mikes found, clarification needed"
    ✗ Ambiguous result

ORCHESTRATOR THINKS:
  "Two contacts found successfully, one needs clarification.
   Can proceed with two attendees and ask about third."

  STEP 4: Create meeting with available attendees
    Tool: secretary(
      action="create_event",
      summary="Team Meeting",
      date="tomorrow",
      time="15:00",
      attendees=["john@company.com", "sarah@company.com"]
    )
    Result: Meeting created ✓

  STEP 5: Send invites
    Tool: mailer(action="send_invites")
    Result: Invites sent to John and Sarah ✓

PHASE 4: Partial Success Response
  "✅ Meeting partially scheduled

  Meeting created for tomorrow at 3pm:
  ✅ John invited (john@company.com)
  ✅ Sarah invited (sarah@company.com)
  ⚠️ Mike - Need clarification

  I found multiple contacts named Mike:
  1. Mike Chen - mike.chen@company.com (Engineering)
  2. Mike Rodriguez - mike.rodriguez@company.com (Sales)

  Which Mike should I add to the meeting?"

  [User responds: "Mike Chen"]

  STEP 6: Add Mike to meeting
    Tool: secretary(action="add_attendee", event_id="evt_123", email="mike.chen@company.com")
    Result: Mike added ✓

  STEP 7: Send invite to Mike
    Tool: mailer(action="send", to="mike.chen@company.com", ...)
    Result: Sent ✓

  "✅ Meeting fully scheduled!

  All attendees invited:
  ✅ John
  ✅ Sarah
  ✅ Mike Chen

  Meeting: Tomorrow at 3pm"
```

---

## Parallel vs Sequential Execution

### When to Execute Sequentially (Default)

**Sequential execution** when steps have dependencies:

```
User: "Research X, create doc, email to Y"

Sequential (CORRECT):
  Step 1: Research → Get content
  Step 2: Create doc with content from Step 1 → Get URL
  Step 3: Email with URL from Step 2

Why: Each step needs result from previous step
```

### When to Consider Parallel

**Parallel execution** only when steps are truly independent:

```
User: "Find my latest invoice, check my calendar for tomorrow, and summarize unread emails"

Could be parallel:
  Step 1: librarian(find invoice) │
  Step 2: secretary(check calendar) │ All execute simultaneously
  Step 3: mailer(summarize emails) │

Why: No dependencies between tasks
```

**Implementation note:** Current system uses sequential by default. Parallel would require explicit orchestrator logic to launch multiple tools simultaneously.

---

## Common Patterns

### Pattern 1: Information Gathering → Action

```
User: "Find contact details for John Doe and send him the quarterly report"

Flow:
  1. rolodex(query="John Doe") → Get email
  2. librarian(query="quarterly report") → Get document
  3. mailer(to=<email from 1>, attachment=<doc from 2>)
```

### Pattern 2: Create → Share → Notify

```
User: "Create project timeline doc and share with team"

Flow:
  1. scribe(create "Project Timeline") → Get doc URL
  2. scribe(share with team emails) → Set permissions
  3. mailer(notify team with link from 1)
```

### Pattern 3: Schedule → Confirm → Remind

```
User: "Schedule client demo next week and set up reminders"

Flow:
  1. secretary(create event "Client Demo") → Get event details
  2. mailer(send confirmation to client)
  3. secretary(add reminders at -24h, -1h)
```

### Pattern 4: Research → Analyze → Report

```
User: "Research competitor pricing and create analysis report"

Flow:
  1. researcher(query="competitor pricing") → Get data
  2. analyst(analyze pricing data from 1) → Get insights
  3. scribe(create report with analysis from 2)
```

---

## Anti-Patterns

### ❌ Anti-Pattern 1: Stopping After First Agent

**WRONG:**
```
User: "Research X, create doc, email to Y"

Orchestrator does:
  Step 1: researcher() → Complete
  → STOPS HERE ❌

User receives: Only research results, no doc or email
```

**ROOT CAUSE:** Using `sub_agents` instead of `AgentTool` pattern

**FIX:** Use AgentTool, explicit sequential calls

### ❌ Anti-Pattern 2: Not Passing Information Forward

**WRONG:**
```
Step 1: researcher() → Returns research content
Step 2: scribe(title="Doc") → NO CONTENT PASSED ❌
Result: Empty document
```

**ROOT CAUSE:** Orchestrator not extracting results

**FIX:**
```
Step 1: researcher() → research_content
Step 2: scribe(title="Doc", content=research_content) ✓
```

### ❌ Anti-Pattern 3: Using Vague References

**WRONG:**
```
Email body: "The document is ready"
❌ Which document? Where?
```

**FIX:**
```
Email body: "Document 'Quantum Research' is ready: https://docs.google.com/document/d/abc123"
✓ Explicit title and link
```

### ❌ Anti-Pattern 4: No Error Checking

**WRONG:**
```
Step 1: agent_a() → Fails ❌
Step 2: agent_b(input_from_step_1) → Uses null/error data
Result: Cascade failure
```

**FIX:**
```
Step 1: agent_a() → Check if successful
  if error:
    handle_error()
    return error message to user
  else:
    proceed to step 2
```

---

## Best Practices Summary

### DO ✅

1. **Plan the full workflow** before executing
2. **Call agents sequentially** when steps depend on each other
3. **Extract information explicitly** from each result
4. **Pass context forward** to next agent
5. **Verify success** before proceeding
6. **Use explicit references** (URLs, IDs, names)
7. **Handle errors gracefully** with user communication
8. **Provide clear progress updates** to user

### DON'T ❌

1. **Don't stop early** - complete full workflow
2. **Don't skip result extraction** - information is lost
3. **Don't use vague references** - be explicit
4. **Don't ignore errors** - handle and communicate
5. **Don't execute out of order** - respect dependencies
6. **Don't guess information** - use proper lookups
7. **Don't batch unrelated operations** - keep focused
8. **Don't assume success** - verify each step

---

## Debugging Checklist

When workflow fails:

**Check Execution Order:**
- [ ] Did orchestrator call all required agents?
- [ ] Were agents called in correct sequence?
- [ ] Did orchestrator wait for each result?

**Check Information Flow:**
- [ ] Did Agent A return needed information?
- [ ] Did orchestrator extract it?
- [ ] Did orchestrator pass it to Agent B?
- [ ] Was information in correct format?

**Check Error Handling:**
- [ ] Did any agent fail?
- [ ] Was error detected by orchestrator?
- [ ] Was user informed?
- [ ] Was recovery attempted?

**Check Agent Boundaries:**
- [ ] Did each agent stay in scope?
- [ ] Did any agent try to use unavailable tools?
- [ ] Did any agent apologize for other agents' work?

---

**The orchestrator is the conductor. Each agent is a musician. The symphony succeeds when the conductor ensures everyone plays their part in harmony.** 🎵
