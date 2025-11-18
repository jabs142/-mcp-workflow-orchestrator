import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from mcp.server.fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("workflow-orchestrator")

# Data directory
DATA_DIR = Path(__file__).parent / "data"
DECISIONS_FILE = Path(__file__).parent / "decisions.json"
LOG_FILE = Path(__file__).parent / "mcp.log"


# ============================================================================
# DATA LOADING
# ============================================================================

def load_json(filename: str) -> Any:
    """Load JSON data from the data directory."""
    with open(DATA_DIR / filename, "r") as f:
        return json.load(f)


def log_event(event: str, **kwargs):
    """Log structured events to stderr and mcp.log file."""
    log_entry = {"timestamp": datetime.now().isoformat(), "event": event, **kwargs}
    log_line = json.dumps(log_entry)

    # Write to stderr for real-time monitoring
    print(log_line, file=sys.stderr)

    # Append to mcp.log file
    with open(LOG_FILE, "a") as f:
        f.write(log_line + "\n")


# Load data at startup (cache in memory)
requests_data = load_json("request.json")
artists_data = load_json("artists.json")
presets_data = load_json("presets.json")
rules_data = load_json("rules.json")

# Create lookup dictionaries for fast access
requests_by_id = {req["id"]: req for req in requests_data}
artists_by_id = {artist["id"]: artist for artist in artists_data}


# ============================================================================
# TOOLS
# ============================================================================

@mcp.tool()
def validate_preset(request_id: str, account_id: str) -> dict:
    """
    Validates that a preset has all required 4-channel texture packing (r, g, b, a).

    Args:
        request_id: The request ID being validated
        account_id: The account/customer ID to check preset for

    Returns:
        {
            "ok": bool,
            "errors": list of error messages (empty if ok=true)
        }
    """
    start_time = datetime.now()

    # If account_id not provided, look it up from request
    if not account_id or account_id == "":
        if request_id in requests_by_id:
            account_id = requests_by_id[request_id].get("account")
            if not account_id:
                result = {
                    "ok": False,
                    "errors": [f"Request '{request_id}' has no account field"]
                }
                log_event("validation.failed", request_id=request_id, reason="no_account_in_request")
                return result
        else:
            result = {
                "ok": False,
                "errors": [f"Request '{request_id}' not found"]
            }
            log_event("validation.failed", request_id=request_id, reason="request_not_found")
            return result

    log_event("tool.called", tool="validate_preset", request_id=request_id, account_id=account_id)

    # Check if preset exists
    if account_id not in presets_data:
        result = {
            "ok": False,
            "errors": [f"No preset found for account '{account_id}'"]
        }
        log_event("validation.failed", request_id=request_id, reason="preset_not_found")
        return result

    preset = presets_data[account_id]
    errors = []

    # Check naming pattern exists
    if "naming" not in preset:
        errors.append("Missing naming pattern configuration")

    # Check for required 4-channel texture packing
    packing = preset.get("packing", {})
    required_channels = {"r", "g", "b", "a"}
    actual_channels = set(packing.keys())
    missing_channels = required_channels - actual_channels

    if missing_channels:
        errors.extend([f"Missing required texture channel: '{ch}'" for ch in sorted(missing_channels)])

    if errors:
        result = {
            "ok": False,
            "errors": errors
        }
        log_event("validation.failed", request_id=request_id, errors=errors)
    else:
        result = {
            "ok": True,
            "errors": []
        }
        log_event("validation.passed", request_id=request_id)

    duration_ms = (datetime.now() - start_time).total_seconds() * 1000
    log_event("tool.completed", tool="validate_preset", request_id=request_id, ok=result["ok"], duration_ms=duration_ms)
    return result


@mcp.tool()
def plan_steps(request_id: str) -> dict:
    """
    Plans workflow steps by matching request attributes against rules.

    Args:
        request_id: The request ID to plan steps for

    Returns:
        {
            "steps": list of workflow step names,
            "matched_rules": list of {rule_index, conditions, actions}
        }
    """
    start_time = datetime.now()
    log_event("tool.called", tool="plan_steps", request_id=request_id)

    if request_id not in requests_by_id:
        log_event("tool.completed", tool="plan_steps", request_id=request_id, error="request_not_found")
        return {"steps": [], "matched_rules": []}

    request = requests_by_id[request_id]
    steps = []
    matched_rules = []

    # Check each rule
    for rule_idx, rule in enumerate(rules_data):
        conditions = rule["if"]

        # Check if all conditions match
        matches = all(
            request.get(key) == value
            for key, value in conditions.items()
        )

        if matches:
            actions = rule["then"]

            # Extract steps from rule actions
            if "steps" in actions:
                steps.extend(actions["steps"])

            # Record matched rule
            matched_rules.append({
                "rule_index": rule_idx,
                "conditions": conditions,
                "actions": actions
            })

    result = {
        "steps": steps,
        "matched_rules": matched_rules
    }

    duration_ms = (datetime.now() - start_time).total_seconds() * 1000
    log_event("tool.completed", tool="plan_steps", request_id=request_id, steps_count=len(steps), duration_ms=duration_ms)
    return result


@mcp.tool()
def assign_artist(request_id: str) -> dict:
    """
    Assigns an artist based on required skills and available capacity.
    Prioritizes skill match, then selects artist with lowest current load.

    Args:
        request_id: The request ID to assign an artist for

    Returns:
        {
            "artist_id": str or null,
            "artist_name": str or null,
            "reason": explanation of assignment decision
        }
    """
    start_time = datetime.now()
    log_event("tool.called", tool="assign_artist", request_id=request_id)

    if request_id not in requests_by_id:
        result = {
            "artist_id": None,
            "artist_name": None,
            "reason": f"Request '{request_id}' not found"
        }
        log_event("tool.completed", tool="assign_artist", request_id=request_id, assigned=False)
        return result

    request = requests_by_id[request_id]
    required_skills = []

    # Determine required skills from request attributes
    if "style" in request:
        required_skills.append(request["style"])
    if "engine" in request:
        required_skills.append(request["engine"].lower())
    if "topology" in request:
        required_skills.append(request["topology"])

    # Find artists with matching skills and available capacity
    eligible_artists = []

    for artist in artists_data:
        # Check capacity
        has_capacity = artist["active_load"] < artist["capacity_concurrent"]
        if not has_capacity:
            continue

        # Check skill match
        artist_skills = set(skill.lower() for skill in artist["skills"])
        required_skills_lower = set(skill.lower() for skill in required_skills)
        skills_match = required_skills_lower.issubset(artist_skills)

        if skills_match:
            eligible_artists.append({
                "id": artist["id"],
                "name": artist["name"],
                "load": artist["active_load"],
                "capacity": artist["capacity_concurrent"]
            })

    # No eligible artists
    if not eligible_artists:
        result = {
            "artist_id": None,
            "artist_name": None,
            "reason": f"No artists available with required skills: {required_skills}"
        }
        log_event("tool.completed", tool="assign_artist", request_id=request_id, assigned=False)
        return result

    # Select artist with lowest load
    best_artist = min(eligible_artists, key=lambda a: a["load"])

    result = {
        "artist_id": best_artist["id"],
        "artist_name": best_artist["name"],
        "reason": f"{best_artist['name']} has required skills {required_skills} and capacity ({best_artist['load']}/{best_artist['capacity']})"
    }

    duration_ms = (datetime.now() - start_time).total_seconds() * 1000
    log_event("tool.completed", tool="assign_artist", request_id=request_id, assigned=True, artist_id=best_artist["id"], duration_ms=duration_ms)
    return result


@mcp.tool()
def record_decision(request_id: str, decision_data: dict) -> dict:
    """
    Records a decision to the decisions.json file with audit trail.

    Args:
        request_id: The request ID this decision is for
        decision_data: Dictionary containing decision details (steps, artist, etc.)

    Returns:
        {
            "decision_id": unique ID for this decision,
            "recorded_at": ISO timestamp,
            "success": bool
        }
    """
    start_time = datetime.now()
    log_event("tool.called", tool="record_decision", request_id=request_id)

    # Create decision record
    decision = {
        "decision_id": f"dec-{request_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "request_id": request_id,
        "recorded_at": datetime.now().isoformat(),
        **decision_data
    }

    # Load existing decisions or create new file
    try:
        if DECISIONS_FILE.exists():
            with open(DECISIONS_FILE, "r") as f:
                decisions = json.load(f)
        else:
            decisions = []
    except (json.JSONDecodeError, FileNotFoundError):
        decisions = []

    # Append new decision
    decisions.append(decision)

    # Write back to file
    with open(DECISIONS_FILE, "w") as f:
        json.dump(decisions, f, indent=2)

    result = {
        "decision_id": decision["decision_id"],
        "recorded_at": decision["recorded_at"],
        "success": True
    }

    duration_ms = (datetime.now() - start_time).total_seconds() * 1000
    log_event("decision.recorded", decision_id=decision["decision_id"], request_id=request_id)
    log_event("tool.completed", tool="record_decision", request_id=request_id, decision_id=decision["decision_id"], duration_ms=duration_ms)

    return result


# ============================================================================
# RESOURCES
# ============================================================================

@mcp.resource("resource://requests")
def get_requests() -> str:
    """Returns all workflow requests."""
    return json.dumps(requests_data, indent=2)


@mcp.resource("resource://artists")
def get_artists() -> str:
    """Returns all artists with their skills and capacity."""
    return json.dumps(artists_data, indent=2)


@mcp.resource("resource://presets")
def get_presets() -> str:
    """Returns all account presets with texture packing configurations."""
    return json.dumps(presets_data, indent=2)


@mcp.resource("resource://rules")
def get_rules() -> str:
    """Returns all workflow rules for conditional step planning."""
    return json.dumps(rules_data, indent=2)


# ============================================================================
# SERVER ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    log_event("server.starting", tools=4, resources=4)
    mcp.run()
