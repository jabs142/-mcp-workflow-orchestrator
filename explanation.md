# How the MCP Workflow Orchestrator Works

## 1. How `server.py` Works

The **MCP Server** exposes tools and resources that the agent can call.

```
┌─────────────────────────────────────────────────────┐
│              MCP SERVER (server.py)                 │
│                                                     │
│  TOOLS (Functions the agent can call):             │
│  ┌──────────────────────────────────────────────┐  │
│  │ 1. validate_preset(request_id)               │  │
│  │    → Checks if preset has naming + 4 channels│  │
│  │    → Returns: {ok: true/false, errors: [...]}│  │
│  │                                               │  │
│  │ 2. plan_steps(request_id)                    │  │
│  │    → Matches request against rules           │  │
│  │    → Returns: {steps: [...], rules: [...]}   │  │
│  │                                               │  │
│  │ 3. assign_artist(request_id)                 │  │
│  │    → Finds artist with skills + capacity     │  │
│  │    → Returns: {artist_id, name, reason}      │  │
│  │                                               │  │
│  │ 4. record_decision(request_id, data)         │  │
│  │    → Saves decision to decisions.json        │  │
│  │    → Returns: {decision_id, success}         │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  RESOURCES (Read-only data):                       │
│  ┌──────────────────────────────────────────────┐  │
│  │ • resource://requests  - All requests        │  │
│  │ • resource://artists   - Artist profiles     │  │
│  │ • resource://presets   - Account configs     │  │
│  │ • resource://rules     - Workflow rules      │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  DATA FILES (loads at startup):                    │
│  • data/request.json   → requests_data            │
│  • data/artists.json   → artists_data             │
│  • data/presets.json   → presets_data             │
│  • data/rules.json     → rules_data               │
│                                                     │
│  LOGGING:                                          │
│  • Logs all tool calls to mcp.log                 │
│  • Tracks duration_ms for each tool               │
└─────────────────────────────────────────────────────┘
```

**What it does:**
- Loads JSON data from `data/` directory at startup
- Exposes 4 tools that the agent can call via MCP protocol
- Provides 4 resources for read-only access to data
- Logs all operations with timestamps and durations

---

## 2. How `run_agent.py` Works

The **Agent** connects to the MCP server and uses Claude to orchestrate the workflow.

```
┌────────────────────────────────────────────────────────────┐
│                    AGENT (run_agent.py)                    │
│                                                            │
│  STARTUP:                                                  │
│  1. Load .env file (get ANTHROPIC_API_KEY)                │
│  2. Start MCP server as subprocess (python3 server.py)    │
│  3. Connect via stdio (standard input/output pipes)       │
│  4. Discover available tools and resources                │
│                                                            │
│  REACT LOOP (for each request):                           │
│                                                            │
│    ┌────────────────────────────────────────────┐         │
│    │ ITERATION 1: Claude thinks                │         │
│    │ "I need to validate the preset first"     │         │
│    │ → Calls: validate_preset(req-001)         │         │
│    └─────────────┬──────────────────────────────┘         │
│                  │                                         │
│                  ▼                                         │
│    ┌────────────────────────────────────────────┐         │
│    │ MCP Server executes validate_preset        │         │
│    │ Returns: {ok: true, errors: []}            │         │
│    └─────────────┬──────────────────────────────┘         │
│                  │                                         │
│                  ▼                                         │
│    ┌────────────────────────────────────────────┐         │
│    │ ITERATION 2: Claude sees result            │         │
│    │ "Validation passed! Now plan steps"       │         │
│    │ → Calls: plan_steps(req-001)               │         │
│    └─────────────┬──────────────────────────────┘         │
│                  │                                         │
│                  ▼                                         │
│    ┌────────────────────────────────────────────┐         │
│    │ MCP Server executes plan_steps             │         │
│    │ Returns: {steps: [...], rules: [...]}      │         │
│    └─────────────┬──────────────────────────────┘         │
│                  │                                         │
│                  ▼                                         │
│    ┌────────────────────────────────────────────┐         │
│    │ ITERATION 3: Assign artist                 │         │
│    │ → Calls: assign_artist(req-001)            │         │
│    └─────────────┬──────────────────────────────┘         │
│                  │                                         │
│                  ▼                                         │
│    ┌────────────────────────────────────────────┐         │
│    │ ITERATION 4: Record decision               │         │
│    │ → Calls: record_decision(req-001, {...})   │         │
│    └─────────────┬──────────────────────────────┘         │
│                  │                                         │
│                  ▼                                         │
│    ┌────────────────────────────────────────────┐         │
│    │ ITERATION 5: Generate rationale            │         │
│    │ Claude writes natural language explanation│         │
│    │ → Stop (end_turn)                          │         │
│    └────────────────────────────────────────────┘         │
│                                                            │
│  OUTPUT:                                                   │
│  • decisions.json - Array of decisions with rationale     │
│  • Each decision has a trace of all tool calls            │
└────────────────────────────────────────────────────────────┘
```

**What it does:**
- Starts MCP server as a subprocess
- Uses Claude API to reason about what tools to call
- Follows a ReAct pattern: **Think → Act → Observe → Repeat**
- Stops on validation failure and generates customer-safe error messages
- Outputs natural language rationale explaining WHY decisions were made

**Example flow for req-002 (validation fails):**
```
Iteration 1: validate_preset → {ok: false, errors: ["Missing channel 'a'"]}
Iteration 2: Claude stops and writes customer error message
            "Your preset is missing the alpha channel. Should we..."
            → No further tool calls (workflow stops)
```

---

## 3. Why We Need MCP?

**Without MCP:** The agent would need to know implementation details of every tool.
**With MCP:** Tools are separate, reusable, and discoverable.

```
✅ LOOSELY COUPLED (MCP):
┌────────────────────────────────────────────┐
│              Agent (run_agent.py)          │
│  "I need to validate. Let me call the tool"│
│  → call validate_preset(req-001)           │
└───────────────────┬────────────────────────┘
                    │ MCP Protocol
                    ▼
┌───────────────────────────────────────────┐
│           MCP Server (server.py)          │
│  • validate_preset() implementation       │
│  • plan_steps() implementation            │
│  • assign_artist() implementation         │
│  • record_decision() implementation       │
└───────────────────────────────────────────┘

Benefits: Agent only knows WHAT to call, not HOW
```

**Why MCP is better:**

1. **Separation of Concerns**
   - Agent = orchestration logic (what to do, when to do it)
   - Server = business logic (HOW to do it)

2. **Reusability**
   - Multiple agents can use the same MCP server
   - You could build a web UI agent, CLI agent, Slack bot agent - all using the same tools

3. **Discoverability**
   - Agent automatically discovers available tools at runtime
   - No hardcoded function calls

4. **Scalability**
   - Add new tools to server → Agent automatically sees them
   - No need to modify agent code when adding tools

5. **Standardization**
   - MCP is an open protocol (works with any AI model, not just Claude)
   - Tools have standardized input/output format

---

## 4. What `test_server.py` Tests

The test suite validates all 4 MCP tools with 9 tests:

**Validation Tests (3 tests):**
```
✓ test_validate_preset_success
  → ArcadiaXR has naming + all 4 channels (r,g,b,a)
  → Should return {ok: true, errors: []}

✓ test_validate_preset_missing_channel
  → TitanMfg is missing 'a' channel
  → Should return {ok: false, errors: ["Missing...channel: 'a'"]}

✓ test_validate_preset_not_found
  → NonExistentAccount doesn't exist
  → Should return {ok: false, errors: ["No preset found..."]}
```

**Workflow Planning Tests (2 tests):**
```
✓ test_plan_steps_matches_rules
  → req-001 should match 2 rules (ArcadiaXR + Unreal)
  → Should return steps: ["style_tweak_review", "export_unreal_glb"]

✓ test_plan_steps_priority_rule
  → req-002 has priority flag
  → Should match priority rule with queue: "expedite"
```

**Artist Assignment Tests (2 tests):**
```
✓ test_assign_artist_with_capacity
  → req-002 needs realistic_pbr, unreal, quad_only skills
  → Ben has these skills + capacity (0/1)
  → Should return {artist_id: "a-2", artist_name: "Ben"}

✓ test_assign_artist_no_capacity
  → req-001 needs stylized_hard_surface + unreal
  → Ada has skill but is full (2/2), no other artists have both skills
  → Should return {artist_id: null} with "No artists available" reason
```

**Decision Recording Tests (2 tests):**
```
✓ test_record_decision_creates_id
  → Should generate unique decision_id with format "dec-{request_id}-{timestamp}"
  → Should return {success: true, recorded_at: "..."}

✓ test_record_decision_idempotency
  → Same request ID should always generate consistent ID format
  → Multiple calls should both succeed and follow same pattern
```

**What these tests verify:**
- ✅ Validation correctly checks naming + 4-channel packing
- ✅ Rules engine matches request attributes correctly
- ✅ Artist assignment respects both skills AND capacity
- ✅ Decision recording generates proper audit trail
- ✅ Error handling works for missing data
- ✅ Edge cases are handled (no capacity, missing presets, etc.)

**How to run:**
```bash
pytest test_server.py -v
```

---

## Summary

**The Flow:**
```
User runs: python run_agent.py
    ↓
Agent starts MCP server (server.py)
    ↓
Agent loads request IDs from data/request.json
    ↓
For each request:
  1. Claude calls validate_preset
  2. If valid → plan_steps → assign_artist → record_decision
  3. If invalid → stop and generate error message
    ↓
Output: decisions.json with rationale + trace
        mcp.log with tool calls + durations
```

**Key Insight:**
The agent (Claude) doesn't know how to validate presets or assign artists. It only knows what tools are available and when to call them. The MCP server handles all the implementation details. This separation makes the system flexible, testable, and easy to extend.
