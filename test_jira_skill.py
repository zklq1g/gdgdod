"""
test_jira_skill.py

Test suite for the Jira Export Custom Skill.
Mocks the Google Generative AI API and tests DataFrame schema enforcement.
"""

import os
os.environ["GOOGLE_API_KEY"] = "dummy_api_key_for_testing"

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

import jira_skill

@pytest.fixture
def mock_genai_model():
    """Fixture to mock the Gemini GenerativeModel."""
    with patch('jira_skill.genai.GenerativeModel') as mock_model_class:
        mock_instance = MagicMock()
        mock_model_class.return_value = mock_instance
        yield mock_instance

def test_generate_jira_tickets_success(mock_genai_model):
    """Test successful extraction and conversion of action items to a DataFrame."""
    # Arrange
    mock_markdown = """
    ## Executive Summary
    Something broke.
    ## Action Items
    1. Fix the database.
    2. Add monitoring.
    """
    
    mock_json_response = """
    [
        {"Title": "Fix DB", "Description": "Fix the database connection", "Priority": "High", "Assignee": "DBA"},
        {"Title": "Add Monitoring", "Description": "Add Datadog alerts", "Priority": "Medium", "Assignee": "SRE"}
    ]
    """
    mock_genai_model.generate_content.return_value = MagicMock(text=mock_json_response)
    
    # Act
    df = jira_skill.generate_jira_tickets(mock_markdown)
    
    # Assert
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert list(df.columns) == ['Title', 'Description', 'Priority', 'Assignee']
    assert df.iloc[0]['Title'] == "Fix DB"
    assert df.iloc[1]['Assignee'] == "SRE"

def test_generate_jira_tickets_missing_section():
    """Test that a ValueError is raised if the Action Items header is missing."""
    mock_markdown = "## Executive Summary\nNo action items here."
    
    with pytest.raises(ValueError, match="Could not find '## Action Items' section"):
        jira_skill.generate_jira_tickets(mock_markdown)

def test_generate_jira_tickets_invalid_json(mock_genai_model):
    """Test that a ValueError is raised if the LLM returns invalid JSON."""
    mock_markdown = "## Action Items\n1. Do something."
    mock_genai_model.generate_content.return_value = MagicMock(text="This is not JSON, I am a hallucinating LLM.")
    
    with pytest.raises(ValueError, match="Failed to parse LLM response into valid JSON"):
        jira_skill.generate_jira_tickets(mock_markdown)

def test_generate_jira_tickets_schema_enforcement(mock_genai_model):
    """Test that missing columns are filled with 'N/A' and Priority is standardized."""
    mock_markdown = "## Action Items\n1. Do something."
    
    # LLM forgets 'Assignee' and uses a weird priority
    mock_json_response = """
    [
        {"Title": "Fix DB", "Description": "Fix it", "Priority": "CRITICAL"}
    ]
    """
    mock_genai_model.generate_content.return_value = MagicMock(text=mock_json_response)
    
    # Act
    df = jira_skill.generate_jira_tickets(mock_markdown)
    
    # Assert
    assert 'Assignee' in df.columns
    assert df.iloc[0]['Assignee'] == "N/A"
    # 'CRITICAL' is not in ['High', 'Medium', 'Low'], so it should default to 'Medium'
    assert df.iloc[0]['Priority'] == "Medium"

def test_generate_jira_tickets_markdown_cleanup(mock_genai_model):
    """Test that the parser successfully strips markdown code blocks if the LLM includes them."""
    mock_markdown = "## Action Items\n1. Do something."
    
    # LLM wraps JSON in markdown blocks despite instructions
    mock_json_response = """
    ```json
    [
        {"Title": "Fix DB", "Description": "Fix it", "Priority": "High", "Assignee": "DBA"}
    ]
    ```
    """
    mock_genai_model.generate_content.return_value = MagicMock(text=mock_json_response)
    
    # Act
    df = jira_skill.generate_jira_tickets(mock_markdown)
    
    # Assert
    assert len(df) == 1
    assert df.iloc[0]['Title'] == "Fix DB"
