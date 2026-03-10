# Google ADK Reference - Multi-Agent System Architecture Guide

Definitive reference for building and optimizing agents in our Google Workspace Multi-Agent System.
Based on analysis of Google ADK source code (installed package) and official documentation.

---

## 1. ADK Agent Types

### 1.1 LlmAgent (alias: Agent)

The primary agent type. Every agent that reasons, uses tools, or generates text is an LlmAgent.

```python
from google.adk.agents import LlmAgent

agent = LlmAgent(
    name="agent_name",                    # Unique, lowercase, valid Python identifier
    model="gemini-2.5-flash",             # Model to use
    instruction="You are...",             # System instruction (string or callable)
    description="One-line description",   # CRITICAL for routing - keep to one sentence
    tools=[tool1, tool2],                 # FunctionTools, AgentTools, etc.
    sub_agents=[child1, child2],          # For transfer_to_agent pattern
    output_key="result_key",             # Store final output in session state
    output_schema=MyModel,               # Force structured JSON output (NO tools allowed with this!)
    input_schema=InputModel,             # Structured input when used as AgentTool
    include_contents='default',          # 'none' = no conversation history
    generate_content_config=config,      # Temperature, max_tokens, etc. (MUST use this, not _config!)
)
```

**Key constraints:**
- `output_schema` is INCOMPATIBLE with tools (Gemini limitation)
- `description` is the single most important field for routing - one clear sentence, no overlap with other agents
- `output_key` writes agent's final text response to `session.state[key]`

### 1.2 SequentialAgent

Deterministic pipeline. Runs sub-agents in list order. NO LLM involved - pure control flow.

```python
from google.adk.agents import SequentialAgent

pipeline = SequentialAgent(
    name="research_pipeline",
    sub_agents=[researcher, scribe, mailer],  # Runs in this exact order
    description="Research topic, create document, send email"
)
```

**State passing between steps:** Use `output_key` on each sub-agent:
```python
researcher = LlmAgent(name="researcher", output_key="research_content", ...)
scribe = LlmAgent(name="scribe", instruction="Create doc with: {research_content}", ...)
```

### 1.3 ParallelAgent

Runs all sub-agents concurrently. Each gets isolated branch (can't see each other's history).

```python
from google.adk.agents import ParallelAgent

parallel = ParallelAgent(
    name="multi_search",
    sub_agents=[web_searcher, news_searcher, youtube_searcher]
)
```

### 1.4 LoopAgent

Repeating cycle until `max_iterations` or agent calls `exit_loop` tool.

```python
from google.adk.agents import LoopAgent

loop = LoopAgent(
    name="iterative_writer",
    sub_agents=[writer, critic],
    max_iterations=5
)
```

---

## 2. The Two Delegation Patterns

This is the most important architectural decision. Choose ONE pattern per relationship.

### 2.1 Pattern A: sub_agents + transfer_to_agent

**How it works:**
- Agent has `sub_agents` list
- ADK auto-injects `transfer_to_agent(agent_name)` function
- LLM decides when to transfer and when it's "done"

**Transfer rules (from ADK source):**
1. Parent -> sub-agent (always allowed)
2. Sub-agent -> parent (always allowed)
3. Sub-agent -> peer sub-agent (only if parent is LlmAgent AND `disallow_transfer_to_peers=False`)

**The fundamental problem for multi-step workflows:**
The LLM autonomously decides when it's "done". After one transfer, it may generate a final
response instead of continuing to the next agent. This is the root cause of incomplete workflows.

```
User: "Research X, create doc, send email"
transfer_to_agent("researcher") -> researcher returns results
LLM thinks "I have results, I'm done" -> STOPS (never calls scribe or mailer!)
```

**When to use:** Only for agents that need autonomous back-and-forth conversation (e.g., ask_user agent).

### 2.2 Pattern B: AgentTool (RECOMMENDED for orchestration)

**How it works:**
- Agent is wrapped as `AgentTool(agent=my_agent)`
- Parent LLM calls it like a function call
- Framework creates isolated execution environment, runs child, returns text result
- Parent LLM sees result and decides next action

```python
from google.adk.tools import AgentTool

orchestrator = LlmAgent(
    name="orchestrator",
    tools=[
        AgentTool(agent=researcher),
        AgentTool(agent=scribe),
        AgentTool(agent=mailer),
    ]
)
```

**Critical implementation details (from ADK source code):**

1. **State isolation:** Child gets COPY of parent state. Changes forwarded back via delta tracking.
2. **Fresh conversation:** Child starts with NO history. Only receives the `request` parameter.
3. **Artifact/Memory shared:** Unlike state, these are shared between parent and child.
4. **Synchronous:** Framework waits for child to complete before returning result to parent.

**When to use:** For ALL worker agent delegation from orchestrator.

### 2.3 AgentTool Configuration

```python
AgentTool(
    agent=my_agent,
    skip_summarization=True,  # CRITICAL! Preserves raw output (no LLM summarization)
)
```

**`skip_summarization=True` is essential** when agent output needs to be passed forward intact.
Without it, a 2000-word research result may be summarized to 200 words before the orchestrator
receives it - resulting in thin/empty documents when passed to scribe.

---

## 3. State Management

### 3.1 State Scoping

```python
# Session-scoped (default) - lives within one session
state["my_key"] = "value"

# App-scoped - shared across ALL sessions for this app
state["app:config_key"] = "value"

# User-scoped - shared across sessions for a specific user
state["user:preferences"] = "value"

# Temporary - NOT persisted between invocations
state["temp:intermediate_result"] = "value"
```

### 3.2 State Access

**In instructions:** Use `{variable_name}` placeholder syntax - resolved against session.state at runtime.

**In tools:**
```python
def my_tool(query: str, tool_context: ToolContext) -> str:
    previous = tool_context.state.get("previous_result", "")
    tool_context.state["my_output"] = "result"
    return "done"
```

### 3.3 State Flow Between Agents

**With SequentialAgent (same session):**
```
Agent A (output_key="result_a") -> state["result_a"] = "A's output"
Agent B instruction: "Use this: {result_a}" -> reads A's output directly
```

**With AgentTool (copied session):**
```
Parent calls AgentTool(agent_A, request="do X")
  -> New session with COPY of parent state
  -> Agent A runs, state deltas forwarded back to parent
  -> Text result returned to parent LLM
Parent calls AgentTool(agent_B, request="do Y")
  -> New session with updated parent state (includes A's deltas)
```

---

## 4. Instruction Writing - Best Practices

### 4.1 The Golden Rule: Less Is More

Research shows LLM attention degrades past ~5,000 tokens of system prompt.
Every repeated concept DILUTES rather than reinforces.

**Target lengths:**
| Agent Type | Target Lines | Max Tokens |
|-----------|-------------|------------|
| Orchestrator (14 agents) | 200-300 | ~3,000 |
| Complex worker (many tools) | 100-200 | ~2,000 |
| Simple worker (few tools) | 50-100 | ~1,000 |

### 4.2 Instruction Structure (Optimal Order)

LLMs pay most attention to the BEGINNING of instructions. Front-load critical rules.

```markdown
# Agent Name - Role (1 line)

## Identity (2-3 sentences)

## Available Tools (list with one-line descriptions)

## Rules (numbered, most important first, each stated ONCE)

## Routing/Decision Guide (table format - scannable)

## One Example (concrete input -> output)

## Error Handling (3-5 lines, not exhaustive taxonomy)

## Output Format (3-5 lines)
```

### 4.3 What to AVOID in Instructions

| Anti-Pattern | Why It Hurts | Fix |
|-------------|-------------|-----|
| Repeating same rule 5+ times | Dilutes attention, confuses priority | State once, clearly |
| "Why this matters" sections | Motivational prose wastes tokens | Just state the rule |
| Multiple examples of same concept | One good example > five mediocre ones | One example per concept |
| Anti-patterns section | Inverse of rules already stated | Remove entirely |
| Quality checklists | LLM doesn't maintain checklists | Remove |
| "NEVER EVER" emphasis | Caps/emojis don't improve compliance | Clear, calm rules |
| Transfer_to_agent AND function call syntax | Conflicting patterns confuse model | Pick ONE pattern |
| Aspirational features (parallel exec) | Documents things that can't happen | Remove |

### 4.4 Effective Rule Writing

```markdown
# BAD (40 lines for one concept):
### Rule 1: Execute All Steps
**Why this matters:** Users expect...
**The Bug We Fixed:** ...
❌ WRONG: ...
✅ CORRECT: ...
**Enforcement:** ...
**Example:** ...
**Anti-Pattern:** ...
**Quality Check:** ...

# GOOD (5 lines for same concept):
### Rule 1: Complete All Workflow Steps
Execute every step before responding. If user asks "research X, create doc, email Y":
1. researcher(query) -> extract content
2. scribe(content) -> extract doc_url
3. mailer(to, doc_url) -> confirm sent
Never respond after step 1 if steps 2-3 remain.
```

### 4.5 Agent Description Writing (for AgentTool routing)

The `description` field is what the orchestrator LLM uses to decide which agent to call.

**Rules:**
- ONE sentence, max 15 words
- Start with action verb
- Include scope boundaries
- No overlap with other agents

```python
# GOOD descriptions:
"Searches web, scrapes URLs, and gathers research from multiple sources"
"Creates and edits Google Docs documents with formatted content"
"Sends, reads, and searches Gmail emails"
"Finds and organizes files in Google Drive"
"Analyzes Google Sheets data using spreadsheet ID (not file name)"

# BAD descriptions:
"A helpful assistant that can do research"  # Too vague
"Handles all document operations including research and email"  # Overlaps with others
"Google Sheets"  # Too short, no context
```

---

## 5. Model Configuration

### 5.1 How to Actually Set Temperature/MaxTokens

**WRONG (does nothing):**
```python
# This stores config but LlmAgent NEVER reads it
agent = create_adk_agent(name="x", model="y", config={"temperature": 0.5})
# Internally: agent._config = config  # Dead storage
```

**CORRECT:**
```python
from google.genai import types

agent = LlmAgent(
    name="orchestrator",
    model="gemini-2.5-pro",
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,        # Low for routing decisions
        max_output_tokens=8192, # For long responses
    ),
    ...
)
```

### 5.2 Recommended Temperature Settings

| Agent Role | Temperature | Reasoning |
|-----------|-------------|-----------|
| Orchestrator/Router | 0.1 - 0.2 | Deterministic routing decisions |
| Data analyst | 0.1 - 0.3 | Factual, precise analysis |
| Email/Calendar ops | 0.2 - 0.4 | Structured operations |
| Research/Writing | 0.5 - 0.7 | Creative but grounded |
| Marketing/Creative | 0.7 - 0.9 | Maximum creativity |
| Philosophy/Dialogue | 0.8 - 1.0 | Open-ended exploration |

---

## 6. Callback System

### 6.1 Available Callbacks

```python
agent = LlmAgent(
    before_agent_callback=on_start,      # Before agent runs
    after_agent_callback=on_finish,      # After agent finishes
    before_tool_callback=on_tool_start,  # Before any tool execution
    after_tool_callback=on_tool_finish,  # After any tool execution
)
```

### 6.2 Callback Signatures

```python
# Before agent - return Content to skip agent entirely, None to proceed
async def on_start(callback_context: CallbackContext) -> Optional[types.Content]:
    callback_context.state["start_time"] = time.time()
    return None  # Proceed normally

# After agent - return Content to replace output, None to keep original
async def on_finish(callback_context: CallbackContext) -> Optional[types.Content]:
    elapsed = time.time() - callback_context.state.get("start_time", 0)
    logger.info(f"Agent completed in {elapsed:.1f}s")
    return None

# Before tool - return dict to skip tool (use dict as result), None to proceed
async def on_tool_start(tool, args, tool_context) -> Optional[dict]:
    logger.info(f"Calling tool: {tool.name} with {args}")
    return None

# After tool - return dict to replace result, None to keep original
async def on_tool_finish(tool, args, tool_context, result) -> Optional[dict]:
    return None
```

### 6.3 Practical Uses

```python
# Logging/observability
async def log_agent(ctx):
    logger.info(f"[ORCHESTRATOR] Agent: {ctx.agent_name}")

# Rate limiting
async def rate_limit(tool, args, tool_context):
    last = tool_context.state.get(f"_last_{tool.name}", 0)
    if time.time() - last < 1.0:
        return {"error": "Rate limited"}
    tool_context.state[f"_last_{tool.name}"] = time.time()
    return None

# Guardrails
async def check_output(ctx):
    # Validate agent output before returning
    return None
```

---

## 7. Tool Types Reference

| Tool Type | Import | Purpose |
|-----------|--------|---------|
| `FunctionTool` | `google.adk.tools` | Wraps Python function as tool |
| `AgentTool` | `google.adk.tools` | Wraps agent as callable tool |
| `LongRunningFunctionTool` | `google.adk.tools` | For slow tools (supports pause/resume) |
| `google_search` | `google.adk.tools` | Built-in Google Search grounding |
| `MCPToolset` | `google.adk.tools` | Model Context Protocol tools |

### FunctionTool (auto-wrapped)

Any typed Python function becomes a tool automatically:

```python
def search_contacts(query: str, max_results: int = 10) -> str:
    """Search Google Contacts by name or email.

    Args:
        query: Name or email to search for
        max_results: Maximum results to return
    """
    # Implementation
    return "Found: John Doe (john@example.com)"

# ADK extracts: name, description (from docstring), parameters (from type hints)
agent = LlmAgent(tools=[search_contacts])  # Auto-wrapped as FunctionTool
```

**Docstring is the tool description** - write it for the LLM, not for developers.
- First line = what the tool does (shown to LLM)
- Args section = parameter descriptions (shown to LLM)

---

## 8. Architectural Patterns for Multi-Agent Systems

### 8.1 Flat Orchestrator (Current - Recommended for gemini-2.5-pro)

```
Orchestrator (gemini-2.5-pro)
  tools: [14 AgentTools]
```

**Pros:** Simple, debuggable, one routing decision
**Cons:** 14 tool options may challenge weaker models
**Best for:** Powerful models (gemini-2.5-pro, gemini-2.5-flash)

### 8.2 Hierarchical Hub-and-Spoke

```
Root Orchestrator
  tools: [
    AgentTool(communication_hub),   # mailer, rolodex, secretary
    AgentTool(document_hub),        # scribe, librarian, analyst
    AgentTool(research_hub),        # researcher, scraper
  ]
```

**Pros:** Easier routing (5 options vs 14), better for weaker models
**Cons:** Extra LLM hop latency (~1-2s per hub), more complex debugging

### 8.3 Hybrid with Pre-built Pipelines (Best for reliability)

```
Orchestrator
  tools: [
    AgentTool(researcher),              # Single agents for simple tasks
    AgentTool(mailer),
    AgentTool(research_and_document),   # SequentialAgent for common workflows
    AgentTool(schedule_and_notify),     # SequentialAgent
  ]
```

**Pros:** Common workflows execute deterministically (can't stop early)
**Cons:** Less flexible for unusual combinations

### 8.4 Recommendation for Our System

Stay with **Flat Orchestrator** (Pattern 8.1) because:
1. We use gemini-2.5-pro which handles 14 tools well
2. Simple to debug and maintain
3. Maximum flexibility for ad-hoc combinations
4. The "stopping early" problem is solved by good instructions, not architecture

If reliability issues persist after instruction optimization, consider adding Pattern 8.3
(pre-built SequentialAgent pipelines) for the 3-4 most common workflows.

---

## 9. Session and Runner

### 9.1 Session Services

| Service | Persistence | Use Case |
|---------|------------|----------|
| `InMemorySessionService` | Process lifetime only | Development/CLI |
| `DatabaseSessionService` | SQL database | Production |
| `VertexAiSessionService` | Google Cloud managed | Cloud deployment |

### 9.2 Runner Configuration

```python
from google.adk.runners import Runner
from google.adk.agents.run_config import RunConfig

runner = Runner(
    agent=orchestrator,
    app_name="my_app",
    session_service=session_service,
)

# Safety limit against infinite loops
run_config = RunConfig(max_llm_calls=50)

# Run with config
async for event in runner.run_async(message, session_id, user_id, run_config=run_config):
    process(event)
```

### 9.3 Invocation Lifecycle

```
invocation = user message -> final response
  Contains one or multiple agent calls

agent_call = agent.run() start -> agent.run() end

LLM agent call contains one or multiple steps:
  step = [call_llm] -> [call_tools (optional)] -> [summarize (optional)]

LLM agent runs steps in loop until:
  1. Final text response generated
  2. Agent transfers to another agent (transfer_to_agent)
  3. end_invocation set to True by callback/tool
```

---

## 10. Checklist: Agent Development

### Before Creating an Agent

- [ ] Clear, non-overlapping `description` (one sentence, max 15 words)
- [ ] `name` is unique, lowercase, valid Python identifier
- [ ] Model chosen appropriately (pro for complex, flash for simple)
- [ ] Tools list contains ONLY what this agent needs
- [ ] `output_key` set if output needs to be passed to another agent
- [ ] `generate_content_config` set with appropriate temperature

### Writing Instructions

- [ ] Under 200 lines for workers, under 300 for orchestrator
- [ ] Critical rules at the TOP (first 20% of instruction)
- [ ] Each rule stated ONCE (no repetition)
- [ ] Routing table in scannable format (markdown table)
- [ ] Maximum 1-2 examples per concept
- [ ] No anti-patterns section (inverse of existing rules)
- [ ] No quality checklist (redundant with rules)
- [ ] No "why this matters" explanations (just the rule)

### AgentTool Configuration

- [ ] `skip_summarization=True` for agents whose output is passed forward
- [ ] Worker agents have `disallow_transfer_to_parent=True`
- [ ] Worker agents have `disallow_transfer_to_peers=True`

### Testing

- [ ] Single-agent test: agent handles its core task correctly
- [ ] Multi-agent test: orchestrator routes to correct agent
- [ ] Chain test: information passes correctly between agents
- [ ] Error test: graceful failure when tool/API fails
- [ ] Edge test: ambiguous requests handled appropriately

---

## 11. Common Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| Instructions too long (>5000 tokens) | Agent ignores rules, especially later ones | Reduce to essential rules only |
| Same rule repeated multiple times | Agent confused about priority | State each rule once |
| Mixed delegation patterns | Agent uses wrong calling convention | Use ONLY AgentTool for workers |
| Missing skip_summarization | Documents/emails have truncated content | Set `skip_summarization=True` |
| Config in `_config` dict | Temperature/tokens have no effect | Use `generate_content_config` |
| Overlapping agent descriptions | Wrong agent called | Make descriptions non-overlapping |
| No output_key on pipeline agents | State doesn't flow between steps | Add output_key |
| Decision Validator without tools | Hallucinates condition checks | Give it tools or remove it |
| transfer_to_agent for workflows | Workflow stops after first agent | Use AgentTool instead |
| Emojis in instructions on Windows | Wasted tokens (stripped by sanitizer) | Use plain text markers |

---

## 12. Our System Architecture Decisions

### Chosen Pattern: Flat Orchestrator with AgentTool

```
User Input -> MasterRouter (keyword match) -> Smart Orchestrator (gemini-2.5-pro)
                                                    |
                                    tools: [14 AgentTools with skip_summarization=True]
                                                    |
                        +-------+-------+-------+---+---+-------+-------+
                        |       |       |       |       |       |       |
                    researcher scribe mailer secretary rolodex librarian analyst
                    scraper synthesizer marketing tracker expense fiskalizacija
```

### Model Assignment

| Agent | Model | Rationale |
|-------|-------|-----------|
| Orchestrator | gemini-2.5-pro | Complex routing, multi-step reasoning |
| researcher | gemini-2.5-flash | Fast web search, synthesis |
| analyst | gemini-2.5-flash | Data analysis with Sheets API |
| scribe | gemini-2.5-flash | Document creation |
| mailer | gemini-2.5-flash | Email operations |
| secretary | gemini-2.5-flash | Calendar operations |
| rolodex | gemini-2.5-flash | Contact lookup |
| librarian | gemini-2.5-flash | Drive file operations |
| tracker | gemini-2.5-flash | Task management |
| expense | gemini-2.5-flash | Receipt OCR + expense tracking |
| scraper | gemini-2.5-flash | Web scraping |
| synthesizer | gemini-2.5-flash | Professional writing |
| marketing | gemini-2.5-flash | Marketing content |
| socrates | gemini-2.5-flash | Philosophical dialogue (via classroom, not orchestrator) |
| fiskalizacija | gemini-2.5-flash | Croatian invoice fiscalization |

### Key Design Decisions

1. **AgentTool for ALL worker delegation** - No transfer_to_agent for workers
2. **skip_summarization=True on all AgentTools** - Preserve full output
3. **Orchestrator temperature 0.1-0.2** - Deterministic routing
4. **Keyword-based philosophy routing** - No LLM call for simple classification
5. **Instructions under 300 lines** - Focused, no redundancy
6. **Decision Validator removed** - Orchestrator checks conditions directly using worker agents

---

## Appendix A: ADK Source File Reference

| Source File | What You Learn |
|------------|---------------|
| `google/adk/agents/base_agent.py` | Agent tree, name validation, callbacks |
| `google/adk/agents/llm_agent.py` | ALL LlmAgent fields, instruction types |
| `google/adk/agents/sequential_agent.py` | Sequential pipeline, state tracking |
| `google/adk/agents/parallel_agent.py` | Concurrent execution, branch isolation |
| `google/adk/agents/loop_agent.py` | Loop mechanics, exit conditions |
| `google/adk/agents/invocation_context.py` | Invocation lifecycle, LLM call limits |
| `google/adk/tools/agent_tool.py` | AgentTool: state copy, Runner, delta forwarding |
| `google/adk/tools/transfer_to_agent_tool.py` | Transfer mechanism |
| `google/adk/sessions/state.py` | State scoping, delta tracking |
| `google/adk/flows/llm_flows/auto_flow.py` | AutoFlow, transfer direction rules |
| `google/adk/runners.py` | Runner, session management |

## Appendix B: Quick Decision Tree

```
User request arrives at orchestrator. Ask:

1. Is it a single task?
   -> Call the one relevant AgentTool
   -> Return result

2. Is it multi-step (research + doc + email)?
   -> Plan all steps
   -> Execute AgentTools sequentially
   -> Pass each result to next step
   -> Verify all steps complete
   -> Return summary

3. Does user mention a file BY NAME?
   -> FIRST: librarian (get file ID)
   -> THEN: analyst/scribe (use file ID)

4. Does user mention a person BY NAME (not email)?
   -> FIRST: rolodex (get email)
   -> THEN: mailer/secretary (use email)

5. Is it conditional (if X then Y)?
   -> Check condition using relevant agent
   -> If met: proceed with action
   -> If not: inform user, suggest alternatives

6. Did any step fail?
   -> Stop workflow
   -> Report what succeeded and what failed
   -> Suggest recovery options
```
