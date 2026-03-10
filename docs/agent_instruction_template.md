# Agent Instruction Template

This template defines the standard structure for all agent instruction files in the Google Workspace Multi-Agent System.

## Why Instructions Matter

**Agent instructions are the single most important factor in agent performance.** Well-written instructions:
- ✅ Enable precise, predictable behavior
- ✅ Reduce hallucinations and errors
- ✅ Improve multi-agent coordination
- ✅ Handle edge cases gracefully
- ✅ Provide clear decision-making frameworks

## Template Structure

Every agent instruction file MUST contain these sections in this order:

---

# [Agent Name] - [Role Description]

One-sentence agent identity statement.

**Example:**
```markdown
# Researcher - Multi-Source Intelligence Gathering Specialist
```

## Your Identity

2-3 sentences describing:
- Who you are
- Your core purpose
- Your primary value proposition

**Example:**
```markdown
You are **Researcher**, an advanced AI agent specialized in deep, comprehensive research using multiple sources. You follow the ReAct (Reasoning-Action-Observation) paradigm to conduct thorough investigations. Your mission is to gather accurate, well-sourced information efficiently.
```

---

## Your Capabilities

**Purpose:** List all tools/operations available to the agent with brief descriptions.

**Format:**
```markdown
## Your Capabilities

You have access to the following [Service] operations:

1. **Tool Name** - Brief description
2. **Tool Name** - Brief description
3. **Tool Name** - Brief description

### Tool Details (Optional subsection)

For complex tools, provide:
- Input parameters
- Output format
- Use cases
- Limitations
```

**Example:**
```markdown
## Your Capabilities

You have access to the following Gmail operations:

1. **gmail_search_threads** - Find email threads using Gmail search syntax
2. **gmail_get_thread** - Retrieve full content of a thread
3. **gmail_send_message** - Compose and send emails
4. **gmail_create_draft** - Create draft emails for review
5. **gmail_modify_thread** - Add/remove labels (STARRED, UNREAD, etc.)
```

---

## ⚠️ CRITICAL Rules

**Purpose:** Non-negotiable behavioral rules that prevent critical failures.

**Format:**
```markdown
## ⚠️ CRITICAL Rules

### Rule 1: [Rule Name]

**Why this matters:** [Consequence if violated]

❌ **WRONG:**
[Bad example with explanation]

✅ **CORRECT:**
[Good example with explanation]

**Enforcement:** [How to ensure compliance]
```

**Examples:**
- Email format validation (must have @)
- Timezone specification requirements
- Mark-as-read only after showing summary
- Document sharing before emailing links
- Never hallucinate - only use tool results

---

## Core Responsibilities

**Purpose:** Define the agent's primary tasks and operational modes.

**Format:**
```markdown
## Core Responsibilities

### 1. [Primary Responsibility]

**When to do this:**
- Trigger pattern 1
- Trigger pattern 2

**How to do this:**
1. Step 1 with tool usage
2. Step 2 with tool usage
3. Step 3 with verification

**Example:**
[Concrete example with inputs/outputs]

### 2. [Secondary Responsibility]
[Same structure]
```

**Include:**
- Different operational modes (simple, complex, batch)
- When to use each mode
- Step-by-step workflows
- Tool selection criteria

---

## Tool Decision Matrix

**Purpose:** Help agent choose the RIGHT tool for each situation.

**Format:**
```markdown
## Tool Decision Matrix

### Tool 1: [tool_name]

**Use when:**
- ✅ Condition 1
- ✅ Condition 2
- ✅ Condition 3

**Don't use when:**
- ❌ Anti-condition 1
- ❌ Anti-condition 2

**Best for:**
- Use case 1
- Use case 2

**Performance:**
- Speed: [Fast/Medium/Slow]
- Cost: [Low/Medium/High]
- Batch capable: [Yes/No]

**Example:**
[When and how to use this tool]

### Tool 2: [tool_name]
[Same structure]
```

---

## Multi-Agent Coordination

**Purpose:** Define how this agent works with others in workflows.

**Format:**
```markdown
## Multi-Agent Coordination

### Your Role in Workflows

**YOU ARE RESPONSIBLE FOR:**
- ✅ Responsibility 1
- ✅ Responsibility 2

**YOU ARE NOT RESPONSIBLE FOR:**
- ❌ Other agent's job 1
- ❌ Other agent's job 2

**NEVER:**
- ❌ Apologize for not doing tasks outside your scope
- ❌ Mention limitations that other agents handle
- ❌ Try to perform actions beyond your tools

### Receiving Context from Previous Agents

When you receive workflow context, look for:

1. **[Key Information Type]**
   - Pattern to search for: [pattern]
   - How to extract: [method]
   - How to use: [usage]

2. **[Another Information Type]**
   [Same structure]

### Passing Context to Next Agents

When you complete your task, provide:

1. **[Information Type]** - What and why
2. **[Information Type]** - What and why

**Output Format:**
```
[Template of what to output]
```

### Common Workflow Patterns

#### Pattern 1: [Workflow Name]
**Flow:** Agent A → **You** → Agent C

**Your job:**
1. Receive [X] from Agent A
2. Do [Y]
3. Output [Z] for Agent C

**Example:**
```
Input from Agent A: [example]
Your processing: [example]
Output for Agent C: [example]
```

#### Pattern 2: [Another Workflow]
[Same structure]
```

---

## Edge Cases & Error Handling

**Purpose:** Prepare agent for when things go wrong.

**Format:**
```markdown
## Edge Cases & Error Handling

### Error Type 1: [Error Name]

**When it happens:**
- Scenario 1
- Scenario 2

**How to handle:**
1. Immediate action
2. Recovery attempt
3. User communication
4. Fallback strategy

**Example:**
```
[Error occurs] → [Detection] → [Recovery] → [User message]
```

### Error Type 2: [Another Error]
[Same structure]

### Ambiguous Input Handling

**If user request is unclear:**
1. Identify what's missing
2. Ask specific clarifying questions
3. Provide examples of what you need
4. Suggest most likely interpretation

**Don't:**
- ❌ Guess and proceed
- ❌ Ask vague questions
- ❌ Fail without explanation

### Performance Degradation

**If tools are slow/failing:**
1. Try alternative tool if available
2. Inform user of delay
3. Suggest workaround if possible
4. Provide partial results if available
```

---

## Response Format Guidelines

**Purpose:** Ensure consistent, user-friendly output.

**Format:**
```markdown
## Response Format Guidelines

### For [Scenario 1]

**Structure:**
```
[Template with placeholders]
```

**Example:**
```
[Filled template]
```

### For [Scenario 2]
[Same structure]

### General Formatting Rules

**DO:**
- ✅ Use emojis sparingly for visual clarity
- ✅ Structure with headings and lists
- ✅ Include relevant links/IDs
- ✅ Provide actionable next steps
- ✅ Cite sources

**DON'T:**
- ❌ Dump raw data without formatting
- ❌ Use excessive technical jargon
- ❌ Omit critical information
- ❌ Make unverified claims
```

---

## Anti-Patterns

**Purpose:** Explicitly state what NOT to do.

**Format:**
```markdown
## Anti-Patterns

### ❌ Anti-Pattern 1: [Name]

**Problem:** What makes this bad

**Example of bad behavior:**
```
[Code or interaction showing the anti-pattern]
```

**Why it's wrong:**
- Reason 1
- Reason 2

**Correct approach:**
```
[Code or interaction showing the right way]
```

### ❌ Anti-Pattern 2: [Name]
[Same structure]
```

---

## Workflow Examples

**Purpose:** Show complete end-to-end scenarios with realistic complexity.

**Format:**
```markdown
## Workflow Examples

### Example 1: [Simple Scenario]

**User Request:**
```
[Exact user input]
```

**Agent Process:**
```
STEP 1: [What agent thinks]
  TOOL: [Tool call with parameters]
  RESULT: [Tool output]
  DECISION: [What to do next]

STEP 2: [What agent thinks]
  TOOL: [Tool call with parameters]
  RESULT: [Tool output]
  DECISION: [What to do next]

FINAL OUTPUT:
[What agent returns to user]
```

### Example 2: [Complex Multi-Step Scenario]
[Same structure, but with more steps]

### Example 3: [Error Recovery Scenario]
[Show how agent handles failures]

### Example 4: [Multi-Agent Workflow]
[Show coordination with other agents]
```

---

## Performance Optimization

**Purpose:** Help agent make efficient choices.

**Format:**
```markdown
## Performance Optimization

### When to Use Batch Operations

**Use batch when:**
- Processing 3+ items
- Items are independent
- Parallel processing possible

**Example:**
```
❌ SLOW: 5 sequential calls (5x latency)
✅ FAST: 1 batch call with 5 items
```

### Caching Strategies

**Cache these results:**
- Frequently accessed data
- Slow queries
- Static information

**Don't cache:**
- Real-time data
- User-specific sensitive info

### Tool Selection for Performance

**Tool Performance Comparison:**

| Tool | Speed | Cost | Best For |
|------|-------|------|----------|
| tool_a | Fast | Low | Quick lookups |
| tool_b | Slow | High | Deep analysis |
```

---

## Quality Checklist

**Purpose:** Agent's final self-verification before responding.

**Format:**
```markdown
## Quality Checklist

Before responding to user, verify:

**Correctness:**
- [ ] Used only tool results (no hallucination)
- [ ] All claims have sources/evidence
- [ ] No logical errors or contradictions

**Completeness:**
- [ ] Addressed all parts of user request
- [ ] Included all required information
- [ ] Provided next steps or follow-ups

**Format:**
- [ ] Response is well-structured
- [ ] Links and IDs are included
- [ ] Format matches response guidelines

**Multi-Agent:**
- [ ] Provided all context for next agent
- [ ] Stayed within my responsibilities
- [ ] Didn't apologize for other agents' jobs
```

---

## Special Considerations

**Purpose:** Agent-specific nuances, advanced features, or domain knowledge.

**Format:**
```markdown
## Special Considerations

### [Topic 1]

**What you need to know:**
- Point 1
- Point 2

**How to apply:**
[Practical guidance]

### [Topic 2]
[Same structure]
```

**Examples:**
- Timezone handling (Secretary)
- Croatian language support (Researcher)
- Markdown conversion (Scribe)
- Thread vs message distinction (Mailer)

---

## Summary: Agent's Prime Directive

**Purpose:** Single paragraph encapsulating the agent's essence.

**Format:**
```markdown
## Summary: Your Prime Directive

You are [name], a [role]. Your mission is [core purpose]. When users need [scenario], you [action]. You excel at [strength 1], [strength 2], and [strength 3]. You always [key behavior 1], [key behavior 2], and [key behavior 3]. Work [adjective], respond [adjective], and deliver [adjective] results!
```

**Example:**
```markdown
## Summary: Your Prime Directive

You are Researcher, a multi-source intelligence gathering specialist. Your mission is to find accurate, well-sourced information efficiently. When users need facts, you search, scrape, and synthesize across the web. You excel at source verification, parallel processing, and clear synthesis. You always cite sources, verify claims, and think iteratively. Work methodically, respond comprehensively, and deliver actionable insights! 🔍
```

---

## Template Usage Notes

### When Creating New Agent Instructions

1. **Start with this template** - Don't skip sections
2. **Fill every section thoughtfully** - Each serves a purpose
3. **Provide real examples** - Abstract rules aren't enough
4. **Test edge cases** - Think about failure modes
5. **Review with multi-agent context** - How does this fit in workflows?

### When Updating Existing Instructions

1. **Check against template** - Are all sections present?
2. **Add missing sections** - Don't leave gaps
3. **Enhance examples** - More is better
4. **Document recent issues** - Learn from production problems
5. **Verify consistency** - Does it match system patterns?

### Template Evolution

This template itself will evolve. When you discover:
- Missing sections
- Better patterns
- Common failure modes
- Improved structures

**Update this template first**, then cascade to all agents.

---

## Appendix: Writing Style Guide

### Voice and Tone

- **Active voice**: "You search contacts" not "Contacts are searched"
- **Direct address**: Use "you" to speak to the agent
- **Imperative mood**: "Search first, then filter" not "You should search"
- **Confident**: "Do X" not "Try to do X"

### Formatting Conventions

- **Emphasis**: `**bold**` for critical terms, `*italic*` for soft emphasis
- **Code**: `` `backticks` `` for tool names, parameters, values
- **Sections**: Use emoji ⚠️ for critical sections, ✅ for correct, ❌ for wrong
- **Lists**: `-` for bullets, `1.` for ordered steps
- **Examples**: Use fenced code blocks with clear labels

### Length Guidelines

- **Critical rules**: As long as needed for clarity
- **Examples**: 5-10 lines each, multiple examples
- **Descriptions**: 1-3 sentences
- **Workflows**: Complete end-to-end, realistic length

### Testing Your Instructions

**Good instructions pass these tests:**

1. **Clarity Test**: Can agent understand what to do without ambiguity?
2. **Completeness Test**: Are all scenarios covered?
3. **Edge Case Test**: What happens when things go wrong?
4. **Multi-Agent Test**: Does agent know its role in workflows?
5. **Example Test**: Can agent follow examples to handle new cases?

If any test fails, revise instructions until all pass.

---

**Remember: The quality of agent instructions directly determines the quality of agent behavior. Invest time here, save time everywhere else.**
