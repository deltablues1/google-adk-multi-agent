# Multi-Agent Workflow Guide

Complete guide to multi-agent coordination in the Google Workspace Multi-Agent System.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [AgentTool Pattern](#agenttool-pattern)
3. [Common Workflow Patterns](#common-workflow-patterns)
4. [Information Passing](#information-passing)
5. [Orchestrator Behavior](#orchestrator-behavior)
6. [Agent Responsibilities](#agent-responsibilities)
7. [Workflow Examples](#workflow-examples)
8. [Best Practices](#best-practices)
9. [Anti-Patterns](#anti-patterns)
10. [Debugging Workflows](#debugging-workflows)

---

## Architecture Overview

### System Structure

```
User Query
    ↓
Smart Orchestrator (LlmAgent with AgentTool pattern)
    ↓
    ├─→ Researcher (AgentTool)
    ├─→ Scribe (AgentTool)
    ├─→ Secretary (AgentTool)
    ├─→ Mailer (AgentTool)
    ├─→ Rolodex (AgentTool)
    ├─→ ... (Other specialist agents as AgentTools)
    ↓
Coordinated Result
```

### Key Principles

1. **Single Orchestrator**: Smart Orchestrator coordinates ALL workflows
2. **AgentTool Pattern**: Worker agents are wrapped as tools, NOT sub-agents
3. **Sequential Execution**: Orchestrator calls agents ONE BY ONE
4. **Context Preservation**: Results flow forward through workflow
5. **Explicit Coordination**: LLM sees results and decides next step

---

## AgentTool Pattern

### What is AgentTool?

**AgentTool** wraps an agent as a synchronous tool that can be called by parent agent.

**Key Differences:**

| Pattern | Delegation | Waiting | Result Flow | Control |
|---------|-----------|----------|-------------|---------|
| `sub_agents` | LLM-driven | Async | Opaque | LLM decides when to stop |
| `AgentTool` | Explicit tool call | Synchronous | Explicit return | Parent waits for result |

### How It Works

**Code Structure:**

```python
from google.adk.tools import AgentTool

# Worker agents (already created)
researcher = create_researcher_agent()
scribe = create_scribe_agent()
mailer = create_mailer_agent()

# Wrap each as AgentTool
researcher_tool = AgentTool(agent=researcher)
scribe_tool = AgentTool(agent=scribe)
mailer_tool = AgentTool(agent=mailer)

# Orchestrator uses tools (NOT sub_agents)
orchestrator = create_adk_agent(
    name="smart_orchestrator",
    model="gemini-2.5-pro",
    tools=[researcher_tool, scribe_tool, mailer_tool],  # ← Agents as tools
    sub_agents=[],  # ← Empty!
    instruction="""
    You coordinate workflows by calling specialist agents as tools.

    IMPORTANT: Call agents ONE BY ONE, wait for result, then proceed.

    Example:
    1. Call researcher(query="research bees")
    2. Wait for result
    3. Call scribe(action="create doc", content=<result from step 1>)
    4. Wait for result
    5. Call mailer(action="send", link=<result from step 3>)
    """
)
```

### Execution Flow

```
User: "Research bees, create doc, email to John"

Orchestrator LLM thinks:
  "I need to: 1) Research, 2) Create doc, 3) Email"

STEP 1: Orchestrator calls researcher tool
  researcher(query="research bees")
  ↓
  [Framework executes researcher agent]
  ↓
  Researcher returns: "Research complete: [bee facts]..."
  ↓
  [Framework returns result to orchestrator]

Orchestrator receives result, thinks:
  "Good, I have research. Now create document."

STEP 2: Orchestrator calls scribe tool
  scribe(action="create", title="Bees", content="[bee facts from step 1]")
  ↓
  [Framework executes scribe agent]
  ↓
  Scribe returns: "Document created: https://docs.google.com/..."
  ↓
  [Framework returns result to orchestrator]

Orchestrator receives result, thinks:
  "Good, I have document link. Now find John's email and send."

STEP 3: Orchestrator calls rolodex tool
  rolodex(query="John")
  ↓
  [Framework executes rolodex agent]
  ↓
  Rolodex returns: "Found: john@example.com"

STEP 4: Orchestrator calls mailer tool
  mailer(action="send", to="john@example.com", content="Document link: ...")
  ↓
  [Framework executes mailer agent]
  ↓
  Mailer returns: "Email sent successfully"

Orchestrator thinks:
  "All steps complete!"

Orchestrator responds to user:
  "✅ Research completed, document created, and emailed to John."
```

### Why AgentTool Pattern?

**Problems with sub_agents + transfer_to_agent:**

❌ LLM decides when workflow is "done" → stops early
❌ No explicit result passing → agents don't get previous context
❌ Opaque delegation → hard to debug
❌ Unreliable multi-step workflows → inconsistent behavior

**Solutions with AgentTool pattern:**

✅ Explicit tool calls → orchestrator controls flow
✅ Synchronous results → guaranteed result passing
✅ Clear execution → easy to debug
✅ Reliable workflows → predictable behavior

---

## Common Workflow Patterns

### Pattern 1: Research → Create → Share

**Flow:** Researcher → Scribe → Mailer

**User Query Examples:**
- "Research X, create document, email to Y"
- "Find info on X, save as doc, send to team"

**Orchestrator Logic:**

```
1. Call researcher(query="research X")
   ↓ Result: research_content

2. Call scribe(action="create", title="X", content=research_content)
   ↓ Result: document_url

3. Call rolodex(query="Y") [if needed]
   ↓ Result: recipient_email

4. Call mailer(action="send", to=recipient_email, body="Document: " + document_url)
   ↓ Result: email_sent_confirmation

5. Return success to user
```

**Information Flow:**

```
Research Content → Document Creation → Email Sending
     ↓                    ↓                  ↓
"[Bee facts]"    "docs.google.com/123"  "Email sent"
```

### Pattern 2: Schedule → Confirm

**Flow:** Secretary → Rolodex → Mailer

**User Query Examples:**
- "Schedule meeting with John tomorrow at 2pm, send confirmation"
- "Book calendar event and notify attendees"

**Orchestrator Logic:**

```
1. Call secretary(action="create_event", summary="Meeting", date="tomorrow", time="14:00")
   ↓ Result: event_created (with event_id, date, time)

2. Call rolodex(query="John")
   ↓ Result: john@example.com

3. Call mailer(action="send", to="john@example.com", body="Meeting confirmed for [explicit date]")
   ↓ Result: confirmation_sent

4. Return success to user
```

**Critical:** Secretary must pass EXPLICIT date (not "tomorrow") to avoid confusion!

### Pattern 3: Read → Summarize → Act

**Flow:** Mailer → Analyst/Synthesizer → [Action Agent]

**User Query Examples:**
- "Read my unread emails and summarize them"
- "Check calendar and suggest meeting times"

**Orchestrator Logic:**

```
1. Call mailer(action="search", query="is:unread")
   ↓ Result: list of unread emails with content

2. Call synthesizer(action="summarize", content=emails)
   ↓ Result: summary

3. Return summary to user (with option to mark as read)
```

### Pattern 4: Find → Update

**Flow:** [Read Agent] → [Write Agent]

**User Query Examples:**
- "Find my document X and add section Y"
- "Update contact John with new email"

**Orchestrator Logic:**

```
1. Call librarian(action="search", query="X")
   ↓ Result: document_id

2. Call scribe(action="update", document_id=document_id, content="Y")
   ↓ Result: update_confirmation

3. Return success to user
```

### Pattern 5: Batch Operations

**Flow:** Single agent with multiple items

**User Query Examples:**
- "Create 5 documents with these titles..."
- "Email these 10 people..."

**Orchestrator Logic:**

```
1. Parse user input into list of items

2. For each item:
   Call agent(action="create", item_data)
   ↓ Collect results

3. Return aggregated results to user
```

**Performance Note:** Some tools support batch operations internally (e.g., `scrape_multiple_urls`). Use those when available!

---

## Information Passing

### What Information Flows Between Agents?

**Each agent in workflow needs specific information from previous agents:**

| Agent | Receives | Provides |
|-------|----------|----------|
| **Researcher** | Search query | Research findings with sources |
| **Scribe** | Document title, content | Document URL, ID |
| **Secretary** | Event details (date, time, attendees) | Event ID, calendar link, formatted date |
| **Mailer** | Recipient email, subject, body | Email sent confirmation |
| **Rolodex** | Contact name/query | Email address, phone, details |
| **Librarian** | File name/ID to search | File ID, metadata |

### How Orchestrator Passes Information

**The orchestrator's job is to:**

1. **Extract** relevant information from agent results
2. **Transform** it into format needed by next agent
3. **Pass** it as parameters in next tool call

**Example:**

```
STEP 1: Researcher returns:
  "Research complete. Findings: [bee facts]. Sources: [urls]"

STEP 2: Orchestrator extracts:
  content = "[bee facts]"  ← Extract content for document

STEP 3: Orchestrator calls scribe:
  scribe(action="create", title="Bees", content=content)
          ↑ Passes extracted content

STEP 4: Scribe returns:
  "Document created: https://docs.google.com/document/d/abc123"

STEP 5: Orchestrator extracts:
  doc_url = "https://docs.google.com/document/d/abc123"

STEP 6: Orchestrator calls mailer:
  mailer(action="send", to="user@example.com", body="Document: " + doc_url)
          ↑ Passes extracted URL
```

### Context Format

**Orchestrator should provide context to agents in this format:**

```markdown
## Original User Request
[User's exact query]

## Workflow Context

### Previous Steps Completed:
1. [Agent Name]: [What they did]
   Result: [Brief summary]

2. [Agent Name]: [What they did]
   Result: [Brief summary]

### Information for You:
- **[Key Info Type]**: [Value]
- **[Key Info Type]**: [Value]

### Your Task:
[What this agent should do now]
```

**Example:**

```markdown
## Original User Request
Research bees, create document, email to John

## Workflow Context

### Previous Steps Completed:
1. Researcher: Conducted research on bees
   Result: Comprehensive findings about bee behavior, ecology, importance

2. Scribe: Created Google Doc with research
   Result: Document "Bees" created at https://docs.google.com/document/d/abc123

3. Rolodex: Found contact "John"
   Result: john@example.com

### Information for You:
- **Document URL**: https://docs.google.com/document/d/abc123
- **Recipient Email**: john@example.com
- **Document Title**: Bees

### Your Task:
Send email to john@example.com with the document link and brief message about the research.
```

---

## Orchestrator Behavior

### Orchestrator's Responsibilities

The Smart Orchestrator MUST:

1. **Understand** user intent and decompose into steps
2. **Plan** the sequence of agent calls needed
3. **Execute** agents ONE BY ONE in correct order
4. **Extract** results after each step
5. **Pass** context to next agent
6. **Verify** each step succeeded before proceeding
7. **Handle** errors and recovery
8. **Synthesize** final response for user

### Orchestrator Instructions Structure

**The orchestrator's instructions should include:**

```markdown
## PHASE 1: UNDERSTANDING USER INTENT

Analyze user query to determine:
- Is this single-step or multi-step?
- Which agents are needed?
- What order should they execute?
- What information flows between steps?

## PHASE 2: AGENT DELEGATION (AgentTool Pattern)

CRITICAL: All specialist agents are available as TOOLS.

Call them like this:
  researcher(query="...")
  scribe(action="create", title="...", content="...")
  mailer(action="send", to="...", body="...")

Execute ONE BY ONE:
1. Call agent
2. WAIT for result (framework handles this automatically)
3. Extract needed information
4. Proceed to next step

## PHASE 3: RESULT SYNTHESIS

After all steps complete:
1. Verify all steps succeeded
2. Compose user-friendly response
3. Include relevant links/IDs
4. Provide next steps if applicable
```

### Decision Making

**How orchestrator decides workflow:**

```
User Query: "Research X, create doc, email to Y"

Orchestrator thinks:
  "Three tasks here:
   1. Research → Need researcher agent
   2. Create doc → Need scribe agent (with research result)
   3. Email → Need mailer agent (with doc URL) + rolodex for Y's email"

Orchestrator plans:
  Step 1: researcher(query="X")
  Step 2: scribe(action="create", content=<from step 1>)
  Step 3: rolodex(query="Y")
  Step 4: mailer(to=<from step 3>, body=<link from step 2>)

Orchestrator executes plan sequentially.
```

### Error Handling

**If an agent fails:**

```
STEP 1: researcher(query="X")
  ↓ ERROR: "Search API rate limit exceeded"

Orchestrator thinks:
  "Step 1 failed. Options:
   1. Retry with exponential backoff
   2. Try alternative search method
   3. Inform user and ask to retry later"

Orchestrator chooses:
  "I'll inform user about rate limit and suggest retry in 5 minutes."

Orchestrator responds:
  "I attempted to research X but encountered an API rate limit.
   Please try again in 5 minutes, or I can save this task for later."
```

---

## Agent Responsibilities

### Responsibility Matrix

**Each agent has CLEAR boundaries:**

| Agent | Responsible For | NOT Responsible For |
|-------|----------------|---------------------|
| **Researcher** | Finding and synthesizing information | Creating documents, sending emails |
| **Scribe** | Creating/editing Google Docs | Researching content, emailing documents |
| **Secretary** | Calendar management | Emailing confirmations, finding contacts |
| **Mailer** | Sending/reading emails | Creating document content, research |
| **Rolodex** | Contact management | Sending emails, scheduling |
| **Librarian** | Finding files in Drive | Creating documents, analyzing content |

### Agent Instruction Guidelines

**In each agent's instructions, include:**

```markdown
## ⚠️ CRITICAL: Multi-Agent Workflow Behavior

### YOUR ROLE
You are ONLY responsible for [specific task].

### NOT YOUR JOB
- ❌ [Other agent's responsibility 1]
- ❌ [Other agent's responsibility 2]

### CORRECT BEHAVIOR
When you complete your task:
✅ Return your result clearly
✅ Include all information next agent needs
✅ Don't apologize for not doing other agents' jobs
✅ Don't mention limitations outside your scope

### EXAMPLE

❌ WRONG:
"I've completed the research, but I cannot create documents or send emails..."

✅ CORRECT:
"Research complete. Here are my findings:
[research content]

Sources:
[sources]"

The orchestrator will handle document creation and distribution.
```

---

## Workflow Examples

### Example 1: Simple Research & Document

**User Query:**
```
"Research quantum computing and create a document"
```

**Orchestrator Execution:**

```
ORCHESTRATOR THINKS:
"Two-step workflow:
 1. Research quantum computing
 2. Create document with research"

STEP 1: Call researcher
Tool Call: researcher(query="quantum computing comprehensive research")

RESEARCHER EXECUTES:
- Uses google_search_grounding("quantum computing")
- Uses scrape_multiple_urls([relevant URLs])
- Synthesizes findings
- Returns: "Research Complete:

           # Quantum Computing Overview

           ## What is Quantum Computing
           [detailed content]

           ## Applications
           [detailed content]

           ## Sources
           1. MIT Technology Review - [URL]
           2. Nature Journal - [URL]"

ORCHESTRATOR RECEIVES RESULT

STEP 2: Call scribe
Tool Call: scribe(
  action="create",
  title="Quantum Computing Research",
  content="[full research from step 1]"
)

SCRIBE EXECUTES:
- Creates Google Doc with title
- Formats content (headings, lists)
- Shares document publicly
- Returns: "Document created successfully:
           Title: Quantum Computing Research
           URL: https://docs.google.com/document/d/xyz789
           The document has been shared publicly."

ORCHESTRATOR RECEIVES RESULT

ORCHESTRATOR RESPONDS TO USER:
"✅ Research completed and document created!

I've researched quantum computing and created a comprehensive document covering:
- What quantum computing is
- Key applications
- Current developments

📄 Document: Quantum Computing Research
🔗 Link: https://docs.google.com/document/d/xyz789

The document is publicly accessible."
```

### Example 2: Schedule Meeting & Send Confirmation

**User Query:**
```
"Schedule meeting with Sarah tomorrow at 2pm and send her confirmation"
```

**Orchestrator Execution:**

```
ORCHESTRATOR THINKS:
"Three-step workflow:
 1. Create calendar event
 2. Find Sarah's email
 3. Send confirmation email"

CURRENT DATE CONTEXT: 2026-01-13 (Monday)
TOMORROW: 2026-01-14 (Tuesday)

STEP 1: Call secretary
Tool Call: secretary(
  action="create_event",
  summary="Meeting with Sarah",
  start_time="2026-01-14T14:00:00+01:00",  ← Explicit RFC3339 with timezone
  end_time="2026-01-14T15:00:00+01:00",
  timezone="Europe/Zagreb"
)

SECRETARY EXECUTES:
- Checks for conflicts (none found)
- Creates calendar event
- Returns: "Event created successfully:
           Title: Meeting with Sarah
           Date: 2026-01-14 (Tuesday, utorak)
           Time: 14:00-15:00 CET
           Event ID: abc123
           Calendar Link: https://calendar.google.com/event?eid=abc123

           Relative: sutra (utorak 14. siječnja) u 14:00"

ORCHESTRATOR RECEIVES RESULT
↓ Extracts: event_date_display = "sutra (utorak 14. siječnja) u 14:00"

STEP 2: Call rolodex
Tool Call: rolodex(query="Sarah")

ROLODEX EXECUTES:
- Searches contacts for "Sarah"
- Returns: "Found 1 contact:
           Name: Sarah Johnson
           Email: sarah.johnson@company.com
           Phone: +1-555-0123"

ORCHESTRATOR RECEIVES RESULT
↓ Extracts: sarah_email = "sarah.johnson@company.com"

STEP 3: Call mailer
Tool Call: mailer(
  action="send",
  to="sarah.johnson@company.com",
  subject="Meeting Confirmation - Tomorrow at 2pm",
  body="Hi Sarah,

This is to confirm our meeting scheduled for **sutra (utorak 14. siječnja) u 14:00**.

Calendar link: https://calendar.google.com/event?eid=abc123

See you then!
"
)

MAILER EXECUTES:
- Validates email format (✓ has @)
- Composes email with explicit date
- Sends email
- Returns: "Email sent successfully to sarah.johnson@company.com"

ORCHESTRATOR RECEIVES RESULT

ORCHESTRATOR RESPONDS TO USER:
"✅ Meeting scheduled and confirmation sent!

📅 Event: Meeting with Sarah
📆 Date: Tomorrow (Tuesday, Jan 14) at 2:00 PM CET
📧 Confirmation sent to: sarah.johnson@company.com

Sarah has been notified with calendar link."
```

### Example 3: Error Recovery

**User Query:**
```
"Research AI agents and email summary to team@company.com"
```

**Orchestrator Execution with Error:**

```
STEP 1: Call researcher
Tool Call: researcher(query="AI agents comprehensive research")

RESEARCHER EXECUTES:
- Attempts google_search_grounding()
- ❌ ERROR: "API rate limit exceeded"
- Returns: "ERROR: Search API unavailable due to rate limiting"

ORCHESTRATOR RECEIVES ERROR

ORCHESTRATOR THINKS:
"Research failed. Options:
 1. Wait and retry
 2. Use cached/partial results if available
 3. Inform user

 Best approach: Inform user and suggest retry"

ORCHESTRATOR RESPONDS TO USER:
"⚠️ Unable to complete research

The search API is currently rate-limited. This typically resolves in 5-10 minutes.

Would you like me to:
1. Retry the research in a few minutes
2. Proceed with cached information if available
3. Schedule this task for later

Please let me know how you'd like to proceed."
```

---

## Best Practices

### DO ✅

**1. Plan Before Executing**
```
Think: "What's the full workflow?"
Map: Agent A → Agent B → Agent C
Execute: One by one
```

**2. Extract Information Explicitly**
```
result = agent_tool(parameters)
needed_info = extract_from(result)  ← Explicit extraction
next_agent_tool(input=needed_info)  ← Explicit passing
```

**3. Use Explicit Dates/Times**
```
✅ "2026-01-14T14:00:00+01:00"
✅ "Tomorrow (Tuesday, Jan 14)"
❌ "tomorrow" (ambiguous when email read later)
```

**4. Validate Before Proceeding**
```
result = agent_tool(params)
if result.contains_error():
    handle_error()
else:
    proceed_to_next_step()
```

**5. Provide Context to Agents**
```
agent_tool(
    task="your specific task",
    context="what happened before",
    previous_results="data from earlier steps"
)
```

**6. Verify Critical Information**
```
if email_format_valid(recipient_email):
    send_email()
else:
    look_up_correct_email()
```

### DON'T ❌

**1. Don't Skip Steps**
```
❌ Assume information exists
✅ Explicitly gather information first
```

**2. Don't Let Agents Overstep**
```
❌ Agent tries to do work outside its scope
✅ Agent stays focused on its responsibility
```

**3. Don't Use Vague References**
```
❌ "the document" (which one?)
✅ "Document 'Bees' at https://docs.google.com/..."
```

**4. Don't Ignore Errors**
```
❌ Proceed despite failure
✅ Handle error, inform user, suggest recovery
```

**5. Don't Batch Unrelated Operations**
```
❌ Create 10 documents in one call (overloads agent)
✅ Create documents sequentially or use batch tool if available
```

**6. Don't Hallucinate Information**
```
❌ Guess email addresses
✅ Look up in contacts or ask user
```

---

## Anti-Patterns

### ❌ Anti-Pattern 1: Premature Workflow Termination

**Problem:** Orchestrator stops after first agent, doesn't complete workflow.

**Example:**
```
User: "Research X, create doc, email to Y"

WRONG BEHAVIOR:
  STEP 1: Call researcher ✓
  STEP 2: Return to user ✗ (stopped early!)

CORRECT BEHAVIOR:
  STEP 1: Call researcher ✓
  STEP 2: Call scribe ✓
  STEP 3: Call rolodex ✓
  STEP 4: Call mailer ✓
  STEP 5: Return to user ✓
```

**Root Cause:** Using `sub_agents` instead of `AgentTool` - LLM decides to stop.

**Fix:** Use AgentTool pattern, explicit sequential calls.

### ❌ Anti-Pattern 2: Information Loss Between Steps

**Problem:** Agent B doesn't receive information from Agent A.

**Example:**
```
WRONG:
  researcher returns detailed findings
  ↓
  scribe called with: scribe(action="create", title="Document")
  ↓
  Document created but EMPTY (no content passed!)

CORRECT:
  researcher returns detailed findings
  ↓
  orchestrator extracts: content = findings
  ↓
  scribe called with: scribe(action="create", title="Document", content=content)
  ↓
  Document created with full content ✓
```

**Root Cause:** Orchestrator not explicitly passing results.

**Fix:** Extract information, pass as parameters.

### ❌ Anti-Pattern 3: Agent Role Confusion

**Problem:** Agent tries to do work outside its scope.

**Example:**
```
WRONG (Researcher):
  "I've completed the research. Now let me create a document..."
  [Tries to call Scribe tools]
  ERROR: Tool not available

CORRECT (Researcher):
  "Research complete. Here are my findings: [content]"
  [Returns result to orchestrator]
  [Orchestrator calls Scribe separately]
```

**Root Cause:** Agent instructions unclear about boundaries.

**Fix:** Clearly define responsibilities in instructions.

### ❌ Anti-Pattern 4: Missing Error Handling

**Problem:** Workflow crashes on first error.

**Example:**
```
WRONG:
  STEP 1: researcher fails ❌
  STEP 2: scribe called with null content → crashes

CORRECT:
  STEP 1: researcher fails ❌
  ORCHESTRATOR: Detects error, attempts recovery or informs user
```

**Root Cause:** No error checking between steps.

**Fix:** Validate results before proceeding.

### ❌ Anti-Pattern 5: Temporal Ambiguity

**Problem:** Using relative dates that become confusing later.

**Example:**
```
WRONG (Email sent by Mailer):
  "Meeting confirmed for today at 2pm"
  [User reads email tomorrow - confusing!]

CORRECT (Email sent by Mailer):
  "Meeting confirmed for Tuesday, January 14, 2026 at 2pm"
  [Clear regardless of when email is read]
```

**Root Cause:** Agents not using explicit date references.

**Fix:** Always use explicit dates, especially in emails/documents.

---

## Debugging Workflows

### Debugging Checklist

When workflow fails, check:

**1. Agent Execution Order**
```
□ Did orchestrator call agents in correct sequence?
□ Did it wait for each result before proceeding?
```

**2. Information Passing**
```
□ Did Agent A return the information Agent B needs?
□ Did orchestrator extract it correctly?
□ Did orchestrator pass it to Agent B?
```

**3. Agent Boundaries**
```
□ Did each agent stay within its responsibilities?
□ Did any agent try to use tools it doesn't have?
```

**4. Error Handling**
```
□ If an agent failed, was error detected?
□ Was recovery attempted?
□ Was user informed?
```

**5. Validation**
```
□ Were email addresses validated (contains @)?
□ Were dates in correct format (RFC3339)?
□ Were required fields provided?
```

### Common Failure Modes

**Symptom:** Workflow stops after first agent

**Diagnosis:**
- Check: Is orchestrator using AgentTool pattern?
- Check: Are agents in `tools` not `sub_agents`?
- Check: Does orchestrator have instructions to continue?

**Fix:** Ensure AgentTool pattern, update orchestrator instructions.

---

**Symptom:** Document created but empty

**Diagnosis:**
- Check: Did researcher return content?
- Check: Did orchestrator extract content from result?
- Check: Did orchestrator pass content to scribe?

**Fix:** Add explicit extraction and passing.

---

**Symptom:** Email not sent or sent to wrong person

**Diagnosis:**
- Check: Did rolodex return valid email?
- Check: Did orchestrator pass email to mailer?
- Check: Was email format validated?

**Fix:** Add email lookup and validation steps.

---

**Symptom:** Temporal confusion (wrong date references)

**Diagnosis:**
- Check: Did secretary provide explicit date?
- Check: Did mailer use explicit date in email?
- Check: Is current date available in context?

**Fix:** Use explicit dates everywhere, inject current date into instructions.

---

### Logging and Observability

**Enable detailed logging:**

```python
logger.info(f"STEP {step_num}: Calling {agent_name}")
logger.info(f"  Parameters: {params}")
logger.info(f"  Result: {result}")
logger.info(f"  Extracted: {extracted_info}")
```

**Log examples from working system:**

```
2026-01-13 21:29:09 - Found 3 threads
2026-01-13 21:29:15 - Modifying Gmail thread: 19bb90a88745b740
2026-01-13 21:29:16 - Thread modified successfully
```

**Use these logs to:**
- Verify execution order
- Check information flow
- Identify where failures occur
- Measure performance

---

## Summary

**Multi-agent workflows succeed when:**

1. **Architecture is clear**: AgentTool pattern, single orchestrator
2. **Responsibilities are defined**: Each agent knows its role
3. **Information flows explicitly**: Results passed forward
4. **Errors are handled**: Graceful degradation
5. **Instructions are comprehensive**: Agents know what to do

**The orchestrator is the conductor, agents are the musicians. The symphony only works when everyone knows their part and plays in harmony.** 🎵

---

## Quick Reference

### Workflow Design Checklist

Before implementing a new workflow:

- [ ] Identified all agents needed
- [ ] Determined execution order
- [ ] Mapped information flow between agents
- [ ] Defined error handling strategy
- [ ] Validated each agent has needed tools
- [ ] Confirmed no agent oversteps boundaries
- [ ] Tested with realistic examples
- [ ] Documented workflow in orchestrator instructions

### Agent Instruction Checklist

For each agent's instructions:

- [ ] Clear responsibility definition
- [ ] Explicit multi-agent coordination section
- [ ] Information passing formats documented
- [ ] "NOT your job" section included
- [ ] No apologies for other agents' work
- [ ] Examples of correct workflow behavior
- [ ] Edge cases and error handling
- [ ] Validation requirements (email format, dates, etc.)

---

**Remember: Great multi-agent systems aren't built, they're orchestrated.** 🎯
