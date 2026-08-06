"""
test_rca_agent.py

Test suite for the Incident RCA Agent core logic.
Mocks the Google Generative AI API to ensure zero quota consumption during CI/CD.
Updated for the two-call pipeline architecture.
"""

import os
# Set dummy API key before importing the module to prevent EnvironmentError
os.environ["GOOGLE_API_KEY"] = "dummy_api_key_for_testing"

import pytest
from unittest.mock import patch, MagicMock, call
from google.api_core.exceptions import TooManyRequests, ServiceUnavailable

import rca_agent

ACTION_ITEMS_JSON = '```json\n[{"Title": "Fix DB index", "Description": "Add index.", "Priority": "High", "Assignee": "DBA"}]\n```'

@pytest.fixture
def mock_genai_model():
    """Fixture to mock the Gemini GenerativeModel."""
    with patch('rca_agent.genai.GenerativeModel') as mock_model_class:
        mock_instance = MagicMock()
        mock_model_class.return_value = mock_instance
        yield mock_instance

def mock_stream_chunks(chunks):
    """Helper to produce a list of mock streaming chunks."""
    mock_chunks = []
    for chunk_text in chunks:
        mock_chunk = MagicMock()
        mock_chunk.text = chunk_text
        mock_chunks.append(mock_chunk)
    return mock_chunks

def mock_blocking_response(text):
    """Helper to produce a mock blocking (non-streaming) response."""
    mock_resp = MagicMock()
    mock_resp.text = text
    return mock_resp

@patch('time.sleep', return_value=None)
def test_analyze_incident_success(mock_sleep, mock_genai_model):
    """Test the two-call pipeline produces a full report with all required sections."""
    # Call 1: streaming narrative
    stream_chunks = mock_stream_chunks([
        "## Executive Summary\nSystem crashed.\n\n",
        "## Timeline\n- 08:00 Crash [Log Line 1]\n\n",
        "## Root Cause\nOOM Error [Log Line 2]\n\n",
    ])
    # Call 2: blocking action items
    blocking_resp = mock_blocking_response(ACTION_ITEMS_JSON)

    mock_genai_model.generate_content.side_effect = [stream_chunks, blocking_resp]

    # Act
    result = "".join(list(rca_agent.analyze_incident("Line 1: Crash\nLine 2: OOM")))

    # Assert all sections present
    assert "## Executive Summary" in result
    assert "## Timeline" in result
    assert "## Root Cause" in result
    assert "## Action Items" in result
    assert "```json" in result
    assert mock_genai_model.generate_content.call_count == 2

@patch('time.sleep', return_value=None)
def test_analyze_incident_retries_on_429(mock_sleep, mock_genai_model):
    """Test that _initiate_stream retries up to 3 times on 429 errors."""
    stream_chunks = mock_stream_chunks(["## Executive Summary\nSuccess after retries."])
    blocking_resp = mock_blocking_response(ACTION_ITEMS_JSON)

    # Narrative call: fail twice, succeed third time. Action items: succeed immediately.
    mock_genai_model.generate_content.side_effect = [
        TooManyRequests("429 Rate Limit"),
        TooManyRequests("429 Rate Limit"),
        stream_chunks,
        blocking_resp,
    ]

    result = "".join(list(rca_agent.analyze_incident("Dummy logs")))

    assert "Success after retries" in result
    # 2 failures + 1 success for narrative + 1 for action items = 4 calls
    assert mock_genai_model.generate_content.call_count == 4

@patch('time.sleep', return_value=None)
def test_analyze_incident_fails_after_max_retries(mock_sleep, mock_genai_model):
    """Test that APICallFailedError is raised after 3 consecutive 503 errors."""
    mock_genai_model.generate_content.side_effect = ServiceUnavailable("503 Unavailable")

    with pytest.raises(rca_agent.APICallFailedError):
        list(rca_agent.analyze_incident("Dummy logs"))

    assert mock_genai_model.generate_content.call_count == 3

def test_analyze_incident_empty_logs():
    """Test that a ValueError is raised if empty logs are provided."""
    with pytest.raises(ValueError, match="Log text cannot be empty"):
        list(rca_agent.analyze_incident(""))

def test_analyze_incident_includes_user_feedback(mock_genai_model):
    """Test that user feedback is correctly injected into the narrative prompt."""
    stream_chunks = mock_stream_chunks(["Revised narrative report."])
    blocking_resp = mock_blocking_response(ACTION_ITEMS_JSON)
    mock_genai_model.generate_content.side_effect = [stream_chunks, blocking_resp]

    list(rca_agent.analyze_incident("Dummy logs", user_feedback="Fix the timeline."))

    # The first call (narrative) should contain the feedback
    first_call_args = mock_genai_model.generate_content.call_args_list[0][0][0]
    assert "Fix the timeline." in first_call_args
    assert "Human Feedback:" in first_call_args
