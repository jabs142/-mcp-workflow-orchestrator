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

### 1. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Set Up API Key

Get your key from: https://console.anthropic.com/settings/keys

Create a `.env` file:
```
ANTHROPIC_API_KEY=sk-ant-...your-key-here
```

---

## Usage

### Run the Agent

```bash
python run_agent.py
```

Uses default data files from `data/` directory and processes all requests.

### Output

**decisions.json** - Array of decisions with rationale and tool call trace:
```json
[{"request_id": "req-001", "validation_passed": true, "rationale": "...", "trace": [...]}]
```

**mcp.log** - Structured logs with tool calls, durations, and failures:
```json
{"timestamp": "...", "event": "tool.called", "tool": "validate_preset", "duration_ms": 12.5}
```

---

## MCP Tools

- **`validate_preset(request_id)`** - Validates naming config and 4-channel texture packing (r, g, b, a). Account is derived from request.
- **`plan_steps(request_id)`** - Matches request attributes against rules to determine workflow steps.
- **`assign_artist(request_id)`** - Assigns artist based on required skills and available capacity.
- **`record_decision(request_id, decision_data)`** - Persists decision with audit trail to decisions.json.

## MCP Resources

- **`resource://requests`** - Workflow requests
- **`resource://artists`** - Artist profiles with skills and capacity
- **`resource://presets`** - Account preset configurations
- **`resource://rules`** - Conditional workflow rules

---

## Testing

```bash
# Run test suite
pytest test_server.py -v

# Run agent with all requests
python run_agent.py
```

**Tests cover:**
- Valid/invalid preset validation
- Workflow rules matching
- Capacity-aware artist assignment
- Decision ID idempotency

---

## Project Structure

```
mcp-workflow-orchestrator/
├── data/
│   ├── request.json
│   ├── artists.json
│   ├── presets.json
│   └── rules.json
├── server.py
├── run_agent.py
├── test_server.py
├── requirements.txt
├── .env.example
└── README.md
```
