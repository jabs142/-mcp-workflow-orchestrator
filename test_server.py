import pytest
from server import validate_preset, plan_steps, assign_artist, record_decision


def test_validate_preset_success():
    """Test that ArcadiaXR preset passes validation (has naming and all 4 channels)"""
    result = validate_preset("req-001")

    assert result["ok"] is True
    assert result["errors"] == []


def test_validate_preset_missing_channel():
    """Test that TitanMfg preset fails validation (missing 'a' channel)"""
    result = validate_preset("req-002")

    assert result["ok"] is False
    assert len(result["errors"]) > 0
    assert any("'a'" in error for error in result["errors"])


def test_validate_preset_not_found():
    """Test validation fails for non-existent request"""
    result = validate_preset("req-999")

    assert result["ok"] is False
    assert any("not found" in error for error in result["errors"])


def test_plan_steps_matches_rules():
    """Test that workflow rules are matched correctly for ArcadiaXR"""
    result = plan_steps("req-001")

    # Should match rule 0 (ArcadiaXR + stylized_hard_surface) and rule 2 (Unreal)
    assert "style_tweak_review" in result["steps"]
    assert "export_unreal_glb" in result["steps"]
    assert len(result["matched_rules"]) == 2


def test_plan_steps_priority_rule():
    """Test that priority requests get expedite queue"""
    result = plan_steps("req-002")  # TitanMfg request with priority

    # Should match priority rule
    matched_rules = result["matched_rules"]
    assert any(rule["actions"].get("queue") == "expedite" for rule in matched_rules)


def test_assign_artist_with_capacity():
    """Test that artist is assigned when they have capacity and matching skills"""
    result = assign_artist("req-002")  # Needs pbr, unreal, quad_only

    # Ben has these skills and capacity (0/1)
    assert result["artist_id"] == "a-2"
    assert result["artist_name"] == "Ben"
    assert "capacity" in result["reason"]


def test_assign_artist_no_capacity():
    """Test that fully loaded artist (Ada) is not assigned"""
    result = assign_artist("req-001")  # Needs stylized_hard_surface

    # Ada has the skill but is full (2/2), so should not be assigned
    # This will fail to assign since Ada is the only one with stylized_hard_surface skill
    assert result["artist_id"] is None
    assert result["artist_name"] is None
    assert "No artists available" in result["reason"]


def test_record_decision_creates_id():
    """Test that record_decision generates a unique decision ID"""
    decision_data = {
        "steps": ["test_step"],
        "artist_id": "a-1",
        "test": True
    }

    result = record_decision("req-test-001", decision_data)

    assert result["success"] is True
    assert result["decision_id"].startswith("dec-req-test-001-")
    assert "recorded_at" in result


def test_record_decision_idempotency():
    """Test that same request generates consistent decision ID format"""
    decision_data = {"test": "data"}

    result1 = record_decision("req-test-002", decision_data)
    result2 = record_decision("req-test-002", decision_data)

    # IDs should have same prefix (they'll differ by timestamp)
    assert result1["decision_id"].startswith("dec-req-test-002-")
    assert result2["decision_id"].startswith("dec-req-test-002-")

    # Both should succeed
    assert result1["success"] is True
    assert result2["success"] is True