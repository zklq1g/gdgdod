"""
test_rca_agent.py

Test suite for the Incident RCA Agent core logic.
Mocks the Google GenAI SDK to ensure zero quota consumption during CI/CD.
Updated for the two-call pipeline architecture, true streaming, and google-genai SDK.
"""

import os
# Set dummy API key before importing the module to prevent EnvironmentError
os.environ["GOOGLE_API_KEY"] = "dummy_api_key_for_testing"

import pytest
from unittest.mock import patch, MagicMock
from google.genai.errors import APIError

import rca_agent

ACTION_ITEMS_JSON = '```json\n[{"Title": "Fix DB index", "Description": "Add index.", "Priority": "High", "Assignee": "DBA"}]\n```'

@pytest.fixture
def mock_genai_client():
    """Fixture to mock the Gemini GenAI Client."""
    with patch('rca_agent.client') as mock_client:
        yield mock_client

def mock_stream_response(chunks_text):
    """Helper to produce a mock streaming response (generator)."""
    def stream_iter():
        for chunk_text in chunks_text:
            mock_chunk = MagicMock()
            mock_chunk.text = chunk_text
            mock_chunk.usage_metadata = None
            yield mock_chunk

        # Final chunk to carry usage metadata
        final_chunk = MagicMock()
        final_chunk.text = ""
        final_chunk.usage_metadata = MagicMock(
            prompt_token_count=100,
            candidates_token_count=50,
            total_token_count=150
        )
        yield final_chunk

    return stream_iter()

def mock_blocking_response(text):
    """Helper to produce a mock blocking (non-streaming) response."""
    mock_resp = MagicMock()
    mock_resp.text = text
    mock_resp.usage_metadata = MagicMock(
        prompt_token_count=50,
        candidates_token_count=20,
        total_token_count=70
    )
    return mock_resp

def create_api_error(message, code):
    """Helper to create a google.genai.errors.APIError"""
    err = APIError(message, code, "HTTP/1.1 429 Too Many Requests")
    err.code = code
    return err

@patch('time.sleep', return_value=None)
def test_analyze_incident_success(mock_sleep, mock_genai_client):
    """Test the two-call pipeline produces a full report with all required sections."""
    # Call 1: streaming narrative
    narrative_stream = mock_stream_response([
        "## Executive Summary\nSystem crashed.\n\n",
        "## Timeline\n- 08:00 Crash [Log Line 1]\n\n",
        "## Root Cause\nOOM Error [Log Line 2]\n\n"
    ])
    # Call 2: blocking action items
    blocking_resp = mock_blocking_response(ACTION_ITEMS_JSON)

    mock_genai_client.models.generate_content_stream.return_value = narrative_stream
    mock_genai_client.models.generate_content.return_value = blocking_resp

    # Act
    result = "".join(list(rca_agent.analyze_incident("Line 1: Crash\nLine 2: OOM")))

    # Assert all sections present
    assert "## Executive Summary" in result
    assert "## Timeline" in result
    assert "## Root Cause" in result
    assert "## Action Items" in result
    assert "```json" in result

    # Verify correct API methods were called
    assert mock_genai_client.models.generate_content_stream.call_count == 1
    assert mock_genai_client.models.generate_content.call_count == 1

@patch('time.sleep', return_value=None)
def test_analyze_incident_retries_on_api_error(mock_sleep, mock_genai_client):
    """Test that _init_narrative_stream retries up to 5 times on API errors."""
    narrative_stream = mock_stream_response(["## Executive Summary\nSuccess after retries."])
    blocking_resp = mock_blocking_response(ACTION_ITEMS_JSON)

    # Narrative stream init: fail twice, succeed third time. Action items: succeed immediately.
    mock_genai_client.models.generate_content_stream.side_effect = [
        create_api_error("429 Rate Limit", 429),
        create_api_error("429 Rate Limit", 429),
        narrative_stream,
    ]
    mock_genai_client.models.generate_content.return_value = blocking_resp

    result = "".join(list(rca_agent.analyze_incident("Dummy logs")))

    assert "Success after retries" in result
    # 2 failures + 1 success for narrative stream init = 3 stream calls
    assert mock_genai_client.models.generate_content_stream.call_count == 3
    # 1 success for action items = 1 blocking call
    assert mock_genai_client.models.generate_content.call_count == 1

@patch('time.sleep', return_value=None)
def test_analyze_incident_fails_after_max_retries(mock_sleep, mock_genai_client):
    """Test that APICallFailedError is raised after 5 consecutive errors."""
    mock_genai_client.models.generate_content_stream.side_effect = create_api_error("503 Unavailable", 503)

    with pytest.raises(rca_agent.APICallFailedError):
        list(rca_agent.analyze_incident("Dummy logs"))

    assert mock_genai_client.models.generate_content_stream.call_count == 5

def test_analyze_incident_empty_logs():
    """Test that a ValueError is raised if empty logs are provided."""
    with pytest.raises(ValueError, match="Log text cannot be empty"):
        list(rca_agent.analyze_incident(""))

def test_analyze_incident_includes_user_feedback(mock_genai_client):
    """Test that user feedback is correctly injected into the narrative prompt."""
    narrative_stream = mock_stream_response(["Revised narrative report."])
    blocking_resp = mock_blocking_response(ACTION_ITEMS_JSON)

    mock_genai_client.models.generate_content_stream.return_value = narrative_stream
    mock_genai_client.models.generate_content.return_value = blocking_resp

    list(rca_agent.analyze_incident("Dummy logs", user_feedback="Fix the timeline."))

    # The first call (narrative stream) should contain the feedback in the contents parameter
    first_call_kwargs = mock_genai_client.models.generate_content_stream.call_args_list[0][1]
    assert "Fix the timeline." in first_call_kwargs['contents']
    assert "Human Feedback:" in first_call_kwargs['contents']
