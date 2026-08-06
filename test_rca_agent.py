"""
test_rca_agent.py

Test suite for the Incident RCA Agent core logic.
Mocks the Google GenAI SDK to ensure zero quota consumption during CI/CD.
Updated for the two-call pipeline architecture and google-genai SDK.
"""

import os
# Set dummy API key before importing the module to prevent EnvironmentError
os.environ["GOOGLE_API_KEY"] = "dummy_api_key_for_testing"

import pytest
from unittest.mock import patch, MagicMock, call
from google.genai.errors import APIError

import rca_agent

ACTION_ITEMS_JSON = '```json\n[{"Title": "Fix DB index", "Description": "Add index.", "Priority": "High", "Assignee": "DBA"}]\n```'

@pytest.fixture
def mock_genai_client():
    """Fixture to mock the Gemini GenAI Client."""
    with patch('rca_agent.client') as mock_client:
        yield mock_client

def mock_blocking_response(text):
    """Helper to produce a mock blocking (non-streaming) response."""
    mock_resp = MagicMock()
    mock_resp.text = text
    return mock_resp

def mock_blocking_response(text):
    """Helper to produce a mock blocking (non-streaming) response."""
    mock_resp = MagicMock()
    mock_resp.text = text
    return mock_resp

def create_api_error(message, code):
    """Helper to create a google.genai.errors.APIError"""
    err = APIError(message, code, "HTTP/1.1 429 Too Many Requests")
    err.code = code
    return err

@patch('time.sleep', return_value=None)
def test_analyze_incident_success(mock_sleep, mock_genai_client):
    """Test the two-call pipeline produces a full report with all required sections."""
    # Call 1: narrative
    narrative_resp = mock_blocking_response(
        "## Executive Summary\nSystem crashed.\n\n"
        "## Timeline\n- 08:00 Crash [Log Line 1]\n\n"
        "## Root Cause\nOOM Error [Log Line 2]\n\n"
    )
    # Call 2: blocking action items
    blocking_resp = mock_blocking_response(ACTION_ITEMS_JSON)

    mock_genai_client.models.generate_content.side_effect = [narrative_resp, blocking_resp]

    # Act
    result = "".join(list(rca_agent.analyze_incident("Line 1: Crash\nLine 2: OOM")))

    # Assert all sections present
    assert "## Executive Summary" in result
    assert "## Timeline" in result
    assert "## Root Cause" in result
    assert "## Action Items" in result
    assert "```json" in result
    assert mock_genai_client.models.generate_content.call_count == 2

@patch('time.sleep', return_value=None)
def test_analyze_incident_retries_on_api_error(mock_sleep, mock_genai_client):
    """Test that _generate_narrative retries up to 5 times on API errors."""
    narrative_resp = mock_blocking_response("## Executive Summary\nSuccess after retries.")
    blocking_resp = mock_blocking_response(ACTION_ITEMS_JSON)

    # Narrative call: fail twice, succeed third time. Action items: succeed immediately.
    mock_genai_client.models.generate_content.side_effect = [
        create_api_error("429 Rate Limit", 429),
        create_api_error("429 Rate Limit", 429),
        narrative_resp,
        blocking_resp,
    ]

    result = "".join(list(rca_agent.analyze_incident("Dummy logs")))

    assert "Success after retries" in result
    # 2 failures + 1 success for narrative + 1 for action items = 4 calls
    assert mock_genai_client.models.generate_content.call_count == 4

@patch('time.sleep', return_value=None)
def test_analyze_incident_fails_after_max_retries(mock_sleep, mock_genai_client):
    """Test that APICallFailedError is raised after 5 consecutive errors."""
    mock_genai_client.models.generate_content.side_effect = create_api_error("503 Unavailable", 503)

    with pytest.raises(rca_agent.APICallFailedError):
        list(rca_agent.analyze_incident("Dummy logs"))

    assert mock_genai_client.models.generate_content.call_count == 5

def test_analyze_incident_empty_logs():
    """Test that a ValueError is raised if empty logs are provided."""
    with pytest.raises(ValueError, match="Log text cannot be empty"):
        list(rca_agent.analyze_incident(""))

def test_analyze_incident_includes_user_feedback(mock_genai_client):
    """Test that user feedback is correctly injected into the narrative prompt."""
    narrative_resp = mock_blocking_response("Revised narrative report.")
    blocking_resp = mock_blocking_response(ACTION_ITEMS_JSON)
    mock_genai_client.models.generate_content.side_effect = [narrative_resp, blocking_resp]

    list(rca_agent.analyze_incident("Dummy logs", user_feedback="Fix the timeline."))

    # The first call (narrative) should contain the feedback in the contents parameter
    first_call_kwargs = mock_genai_client.models.generate_content.call_args_list[0][1]
    assert "Fix the timeline." in first_call_kwargs['contents']
    assert "Human Feedback:" in first_call_kwargs['contents']
