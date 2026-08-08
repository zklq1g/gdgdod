"""
test_jira_skill.py

Test suite for the Jira Export Custom Skill.
Tests deterministic JSON extraction and DataFrame schema enforcement.
No API mocking needed — jira_skill.py has zero LLM dependency.
"""

import os
os.environ["GOOGLE_API_KEY"] = "dummy_api_key_for_testing"

import pytest
import pandas as pd
import jira_skill

def test_generate_jira_tickets_success():
    """Test successful extraction and conversion of JSON action items to a DataFrame."""
    mock_markdown = """
    ## Executive Summary
    Something broke.
    ## Action Items
    Here are the tasks:
    ```json
    [
        {"Title": "Fix DB", "Description": "Fix the database connection", "Priority": "High", "Assignee": "DBA"},
        {"Title": "Add Monitoring", "Description": "Add Datadog alerts", "Priority": "Medium", "Assignee": "SRE"}
    ]
    ```
    """
    df = jira_skill.generate_jira_tickets(mock_markdown)
    
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert list(df.columns) == ['Title', 'Description', 'Priority', 'Assignee']
    assert df.iloc[0]['Title'] == "Fix DB"
    assert df.iloc[1]['Assignee'] == "SRE"

def test_generate_jira_tickets_missing_json_block():
    """Test that an empty DataFrame is returned if the JSON block is missing."""
    mock_markdown = "## Action Items\n1. Standard list item."
    df = jira_skill.generate_jira_tickets(mock_markdown)
    
    assert df.empty
    assert list(df.columns) == ['Title', 'Description', 'Priority', 'Assignee']

def test_generate_jira_tickets_invalid_json():
    """Test that an empty DataFrame is returned if the JSON is not an array."""
    mock_markdown = """
    ## Action Items
    ```json
    { "this is": "not an array" }
    ```
    """
    df = jira_skill.generate_jira_tickets(mock_markdown)
    assert df.empty

def test_generate_jira_tickets_malformed_json():
    """Test that an empty DataFrame is returned if the JSON is syntactically broken."""
    mock_markdown = """
    ## Action Items
    ```json
    [ {"Title": "Fix DB", "Priority": "High" 
    ```
    """
    df = jira_skill.generate_jira_tickets(mock_markdown)
    assert df.empty

def test_generate_jira_tickets_schema_enforcement():
    """Test that missing columns are filled with 'N/A' and Priority is standardized."""
    mock_markdown = """
    ## Action Items
    ```json
    [
        {"Title": "Fix DB", "Description": "Fix it", "Priority": "CRITICAL"}
    ]
    ```
    """
    df = jira_skill.generate_jira_tickets(mock_markdown)
    
    assert 'Assignee' in df.columns
    assert df.iloc[0]['Assignee'] == "N/A"
    # 'CRITICAL' is not in ['High', 'Medium', 'Low'], so it should default to 'Medium'
    assert df.iloc[0]['Priority'] == "Medium"
