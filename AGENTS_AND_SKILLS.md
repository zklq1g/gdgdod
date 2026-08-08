# Agents and Skills

## RCA Agent (`rca_agent.py`)
- **Role:** The core AI brain for analyzing system logs.
- **Capabilities:** 
  - Streams narrative Root Cause Analysis reports.
  - Enforces strict citations to log line numbers.
  - Incorporates human feedback for targeted revisions.
  - Implements API resilience (retries, backoff, caching).

## Jira Skill (`jira_skill.py`)
- **Role:** Deterministic data extraction and formatting.
- **Capabilities:**
  - Parses Markdown to extract structured JSON action items.
  - Validates schemas (Title, Description, Priority, Assignee).
  - Converts JSON into Pandas DataFrames for CSV export.
