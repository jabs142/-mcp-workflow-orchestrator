# MCP Workflow Orchestrator

Agent-based request triage system using Model Context Protocol (MCP).

Demonstrates workflow orchestration with validation, planning, and assignment capabilities for 3D asset production workflows.

## Features

- **MCP Server** with 4 tools and 4 resources
- **AI Agent** using ReAct pattern with Claude
- **Validation** of preset configurations (4-channel texture packing)
- **Rules-based workflow planning**
- **Capacity-aware artist assignment**
- **Decision audit trail** with natural language rationale
- **Observability** through structured logging

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Agent (run_agent.py)                        │
│  - Connects to MCP server via stdio                         │
│  - Uses Claude API for reasoning                            │
│  - Orchestrates tools: validate → plan → assign → record    │
│  - Outputs decisions.json with rationale                    │
└────────────────┬────────────────────────────────────────────┘
                 │ MCP Protocol (stdio)
                 │
┌────────────────▼────────────────────────────────────────────┐
│                 MCP Server (server.py)                       │
│                                                              │
│  Tools:                        Resources:                   │
│  ├─ validate_preset()          ├─ resource://requests       │
│  ├─ plan_steps()               ├─ resource://artists        │
│  ├─ assign_artist()            ├─ resource://presets        │
│  └─ record_decision()          └─ resource://rules          │
│                                                              │
│  Reads: data/*.json            Writes: decisions.json       │
└─────────────────────────────────────────────────────────────┘
```

---

## Setup

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd mcp-workflow-orchestrator
```

### 2. Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

**Dependencies:**
- `mcp>=1.0.0` - Model Context Protocol SDK
- `anthropic>=0.39.0` - Claude API client
- `python-dotenv>=1.0.0` - Environment variable management
- `pytest>=7.4.0` - Testing framework

### 4. Set Up API Key
# Get your key from: https://console.anthropic.com/settings/keys
```

Your `.env` file should look like:
```
ANTHROPIC_API_KEY=sk-ant-...your-key-here
```

---

## Usage

### Process All Requests (Default)
```bash
python run_agent.py
```

This processes all 3 requests in `data/request.json`:
- `req-001` - ArcadiaXR (valid preset)
- `req-002` - TitanMfg (invalid preset - missing 'a' channel)
- `req-003` - BlueNova (valid preset)

### Process Specific Requests

```bash
# Process just one request
python run_agent.py --request-ids req-001

# Process multiple specific requests
python run_agent.py --request-ids req-001 req-003

# Process the failing case
python run_agent.py --request-ids req-002
```

### Output

The agent writes results to `decisions.json`:

```json
[
  {
    "request_id": "req-001",
    "validation_passed": true,
    "rationale": "Successfully processed request req-001 for ArcadiaXR...",
    "trace": [
      {
        "tool": "validate_preset",
        "input": {"request_id": "req-001", "account_id": "ArcadiaXR"},
        "output": {"ok": true, "errors": []},
        "timestamp": "2025-11-18T12:00:00"
      },
      {
        "tool": "plan_steps",
        "input": {"request_id": "req-001"},
        "output": {"steps": ["style_tweak_review", "export_unreal_glb"], ...}
      },
      ...
    ],
    "completed_at": "2025-11-18T12:00:05"
  }
]
```

### Logs

Server logs are written to stderr (visible in terminal):

```json
{"timestamp": "2025-11-18T12:00:00", "event": "server.starting", "tools": 4, "resources": 4}
{"timestamp": "2025-11-18T12:00:01", "event": "tool.called", "tool": "validate_preset", "request_id": "req-001"}
{"timestamp": "2025-11-18T12:00:01", "event": "validation.passed", "request_id": "req-001"}
{"timestamp": "2025-11-18T12:00:01", "event": "tool.completed", "tool": "validate_preset", "ok": true}
{"timestamp": "2025-11-18T12:00:02", "event": "decision.recorded", "decision_id": "dec-req-001-..."}
```

---

## MCP Tools

### `validate_preset(request_id, account_id)`

Validates that an account's preset has all required texture packing channels (r, g, b, a).

**Example:**
```python
Input:  {"request_id": "req-002", "account_id": "TitanMfg"}
Output: {"ok": false, "errors": ["Missing required texture channel: 'a'"]}
```

### `plan_steps(request_id)`

Matches request attributes against rules to determine workflow steps.

**Example:**
```python
Input:  {"request_id": "req-001"}
Output: {
  "steps": ["style_tweak_review", "export_unreal_glb"],
  "matched_rules": [
    {"rule_index": 0, "conditions": {"account": "ArcadiaXR", ...}, ...},
    {"rule_index": 2, "conditions": {"engine": "Unreal"}, ...}
  ]
}
```

### `assign_artist(request_id)`

Assigns an artist based on required skills and available capacity.

**Example:**
```python
Input:  {"request_id": "req-001"}
Output: {
  "artist_id": "a-2",
  "artist_name": "Ben",
  "reason": "Ben has required skills [...] and capacity (0/1)"
}
```

### `record_decision(request_id, decision_data)`

Persists the decision with audit trail to `decisions.json`.

**Example:**
```python
Input:  {"request_id": "req-001", "steps": [...], "artist_id": "a-2", ...}
Output: {"decision_id": "dec-req-001-20251118120005", "recorded_at": "...", "success": true}
```

---

## MCP Resources

Resources provide read-only access to data for context:

- **`resource://requests`** - All workflow requests
- **`resource://artists`** - Artist profiles with skills and capacity
- **`resource://presets`** - Account-specific preset configurations
- **`resource://rules`** - Conditional workflow rules

The agent reads these before calling tools to understand context.

---

## Project Structure

```
mcp-workflow-orchestrator/
├── data/                      # Sample data
│   ├── request.json           # 3 sample requests
│   ├── artists.json           # 3 artists with skills/capacity
│   ├── presets.json           # 2 account presets
│   └── rules.json             # 4 workflow rules
├── server.py                  # MCP server (4 tools, 4 resources)
├── run_agent.py               # Agent with ReAct loop
├── requirements.txt           # Python dependencies
├── .env.example               # Environment template
├── .env                       # Your API key (git-ignored)
├── .gitignore                 # Ignore venv, .env, etc.
├── decisions.json             # Output (generated)
└── README.md                  # This file
```

---

## How It Works

### 1. Agent Starts
- Connects to MCP server via stdio subprocess
- Discovers available tools and resources
- Loads initial prompt with task instructions

### 2. ReAct Loop
For each request:

```
Iteration 1: Claude reads resources (requests, presets, artists, rules)
Iteration 2: Claude calls validate_preset → gets result
Iteration 3: If validation passed, calls plan_steps → gets steps
Iteration 4: Calls assign_artist → gets artist assignment
Iteration 5: Calls record_decision → saves to disk
Iteration 6: Claude generates natural language rationale → done
```

### 3. Output
- **decisions.json** - One decision per request with rationale and trace
- **Logs** - Structured events to stderr for observability

---

## Testing

### Test the MCP Server Directly

You can test individual tools using the MCP inspector or by importing:

```python
from server import validate_preset, plan_steps

# Test validation
result = validate_preset("req-001", "ArcadiaXR")
assert result["ok"] == True

result = validate_preset("req-002", "TitanMfg")
assert result["ok"] == False
assert "Missing required texture channel: 'a'" in result["errors"][0]
```

### Run the Full Workflow

```bash
# Test with all requests
python run_agent.py

# Check the output
cat decisions.json

# Test validation failure case
python run_agent.py --request-ids req-002
```

### Expected Behavior

**req-001 (ArcadiaXR):**
- ✅ Validation passes (preset has r, g, b, a)
- ✅ Steps planned: `["style_tweak_review", "export_unreal_glb"]`
- ✅ Artist assigned (based on skills and capacity)
- ✅ Decision recorded

**req-002 (TitanMfg):**
- ❌ Validation fails (preset missing 'a' channel)
- ⚠️ Workflow stops
- 📝 Customer-safe error message generated

**req-003 (BlueNova):**
- ✅ Validation passes
- ✅ Steps planned
- ✅ Artist assigned
- ✅ Decision recorded

---

## Key Design Decisions

### Why MCP?

- **Separation of concerns** - Business logic (server) separate from orchestration (agent)
- **Reusability** - Multiple agents can use the same tools
- **Standardization** - MCP protocol makes tools discoverable and self-documenting
- **Scalability** - Easy to add new tools without changing agent code

### Why ReAct Pattern?

- **Observable** - See each tool call and decision step
- **Explainable** - Natural language rationale for decisions
- **Flexible** - Agent adapts based on tool results (e.g., stops on validation failure)
- **Debuggable** - Trace shows exactly what happened and why

### Why Stdio Transport?

- **Simple** - No network configuration needed
- **Secure** - Server runs locally, no exposed ports
- **Fast** - Direct process communication
- **Portable** - Works on any platform (Mac, Linux, Windows)
