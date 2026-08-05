"""
test_rca_agent.py

Test suite for the Incident RCA Agent core logic.
Mocks the Google Generative AI API to ensure zero quota consumption during CI/CD.
"""

import os
# Set dummy API key before importing the module to prevent EnvironmentError
os.environ["GOOGLE_API_KEY"] = "dummy_api_key_for_testing"

import pytest
from unittest.mock import patch, MagicMock
from google.api_core.exceptions import TooManyRequests, ServiceUnavailable

import rca_agent

@pytest.fixture
def mock_genai_model():
    """Fixture to mock the Gemini GenerativeModel."""
    with patch('rca_agent.genai.GenerativeModel') as mock_model_class:
        mock_instance = MagicMock()
        mock_model_class.return_value = mock_instance
        yield mock_instance

@patch('time.sleep', return_value=None) # Prevent actual sleeping during retry tests
def test_analyze_incident_success(mock_sleep, mock_genai_model):
    """Test that a successful API call returns a string with all required Markdown headers."""
    # Arrange
    mock_response = MagicMock()
    mock_response.text = (
        "## Executive Summary\nSystem crashed.\n\n"
        "## Timeline\n- 08:00 Crash [Log Line 1]\n\n"
        "## Root Cause\nOOM Error [Log Line 2]\n\n"
        "## Action Items\n1. Increase memory."
    )
    mock_genai_model.generate_content.return_value = mock_response
    
    # Act
    result = rca_agent.analyze_incident("Line 1: Crash\nLine 2: OOM")
    
    # Assert
    assert "## Executive Summary" in result
    assert "## Timeline" in result
    assert "## Root Cause" in result
    assert "## Action Items" in result
    assert mock_genai_model.generate_content.call_count == 1

@patch('time.sleep', return_value=None)
def test_analyze_incident_retries_on_429(mock_sleep, mock_genai_model):
    """Test that the agent retries up to 3 times when encountering a 429 TooManyRequests error."""
    # Arrange
    mock_response = MagicMock()
    mock_response.text = "## Executive Summary\nSuccess after retries."
    
    # Fail twice, succeed on the third try
    mock_genai_model.generate_content.side_effect = [
        TooManyRequests("429 Rate Limit"),
        TooManyRequests("429 Rate Limit"),
        mock_response
    ]
    
    # Act
    result = rca_agent.analyze_incident("Dummy logs")
    
    # Assert
    assert "Success after retries" in result
    assert mock_genai_model.generate_content.call_count == 3

@patch('time.sleep', return_value=None)
def test_analyze_incident_fails_after_max_retries(mock_sleep, mock_genai_model):
    """Test that APICallFailedError is raised after 3 consecutive 503 errors."""
    # Arrange
    mock_genai_model.generate_content.side_effect = ServiceUnavailable("503 Unavailable")
    
    # Act & Assert
    with pytest.raises(rca_agent.APICallFailedError) as excinfo:
        rca_agent.analyze_incident("Dummy logs")
        
    assert "high traffic or is temporarily unavailable" in str(excinfo.value) or \
           "Failed to communicate with the AI service" in str(excinfo.value)
    assert mock_genai_model.generate_content.call_count == 3

def test_analyze_incident_empty_logs():
    """Test that a ValueError is raised if empty logs are provided."""
    with pytest.raises(ValueError, match="Log text cannot be empty"):
        rca_agent.analyze_incident("")
        
def test_analyze_incident_includes_user_feedback(mock_genai_model):
    """Test that user feedback is correctly injected into the prompt."""
    # Arrange
    mock_genai_model.generate_content.return_value = MagicMock(text="Revised report")
    
    # Act
    rca_agent.analyze_incident("Dummy logs", user_feedback="Fix the timeline.")
    
    # Assert
    # Check that the prompt passed to the API contains the feedback
    call_args = mock_genai_model.generate_content.call_args[0][0]
    assert "Fix the timeline." in call_args
    assert "Human Feedback:" in call_args
