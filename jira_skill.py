"""
jira_skill.py

The Custom Skill for the Incident RCA Agent.
Parses the 'Action Items' section of an RCA Markdown report and uses the 
Google Gemini API to structure them into Jira-ready tickets (Pandas DataFrame).
"""

import os
import re
import json
import logging
from typing import List, Dict, Any
import pandas as pd
from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ensure environment variables are loaded and API is configured
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise EnvironmentError("GOOGLE_API_KEY is not set in the environment or .env file.")
genai.configure(api_key=API_KEY)

# Define the strict prompt for Jira ticket generation
JIRA_EXTRACTION_PROMPT = """You are an expert Technical Project Manager. 
Your task is to convert a list of unstructured action items into a structured JSON array of Jira tickets.

For each action item, extract or infer the following fields:
- "Title": A concise, actionable summary of the task (max 10 words).
- "Description": A detailed explanation of what needs to be done and why.
- "Priority": Must be exactly one of: "High", "Medium", or "Low".
- "Assignee": The most logical team or role responsible (e.g., "Backend Engineer", "DevOps", "DBA", "SRE").

Return ONLY a valid JSON array of objects. Do not include markdown formatting, explanations, or any text outside the JSON array.
"""

def extract_action_items_section(rca_markdown: str) -> str:
    """
    Extracts the text specifically under the '## Action Items' header from Markdown.

    Args:
        rca_markdown (str): The full RCA report in Markdown format.

    Returns:
        str: The raw text of the action items section.

    Raises:
        ValueError: If the '## Action Items' header is not found.
    """
    # Regex to find '## Action Items' and capture everything until the next '##' or end of string
    pattern = r"##\s*Action\s*Items\s*(.*?)(?=##|$)"
    match = re.search(pattern, rca_markdown, re.IGNORECASE | re.DOTALL)
    
    if not match:
        raise ValueError("Could not find '## Action Items' section in the provided RCA report.")
    
    action_items_text = match.group(1).strip()
    if not action_items_text:
        raise ValueError("The '## Action Items' section is empty.")
        
    return action_items_text

def generate_jira_tickets(rca_markdown: str) -> pd.DataFrame:
    """
    Parses action items from an RCA report and structures them into a Pandas DataFrame.

    Args:
        rca_markdown (str): The full RCA report in Markdown format.

    Returns:
        pd.DataFrame: A DataFrame containing columns: Title, Description, Priority, Assignee.

    Raises:
        ValueError: If action items are missing or LLM returns invalid JSON.
        RuntimeError: If the Gemini API call fails.
    """
    logger.info("Extracting action items from RCA report...")
    action_items_text = extract_action_items_section(rca_markdown)
    
    full_prompt = f"{JIRA_EXTRACTION_PROMPT}\n\nACTION ITEMS TO PROCESS:\n{action_items_text}"

    try:
        logger.info("Calling Gemini API to structure Jira tickets...")
        # Initialize the model (using gemini-3.5-flash for speed and cost-efficiency)
        model = genai.GenerativeModel('gemini-3.5-flash')
        
        # Use native JSON mode to guarantee valid JSON output and prevent markdown wrapping
        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        
        raw_json_text = response.text.strip()
        
        # Fallback cleanup in case the model still wraps in ```json ... ``` despite mime_type
        if raw_json_text.startswith("```json"):
            raw_json_text = raw_json_text[7:]
        if raw_json_text.endswith("```"):
            raw_json_text = raw_json_text[:-3]
        raw_json_text = raw_json_text.strip()

        # Parse JSON
        tickets_data: List[Dict[str, Any]] = json.loads(raw_json_text)
        
        if not isinstance(tickets_data, list):
            raise ValueError("LLM did not return a JSON array.")

        # Convert to DataFrame and enforce schema
        df = pd.DataFrame(tickets_data)
        
        expected_columns = ['Title', 'Description', 'Priority', 'Assignee']
        
        # Ensure all expected columns exist, filling missing ones with 'N/A'
        for col in expected_columns:
            if col not in df.columns:
                df[col] = "N/A"
                
        # Filter to only keep expected columns and standardize Priority
        df = df[expected_columns]
        df['Priority'] = df['Priority'].apply(
            lambda x: x.capitalize() if str(x).capitalize() in ['High', 'Medium', 'Low'] else 'Medium'
        )
        
        logger.info(f"Successfully generated {len(df)} Jira tickets.")
        return df

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        logger.debug(f"Raw LLM response: {raw_json_text}")
        raise ValueError("Failed to parse LLM response into valid JSON for Jira tickets.")
        
    except google_exceptions.GoogleAPIError as e:
        logger.error(f"Google API Error during Jira generation: {e}")
        raise RuntimeError(f"Failed to communicate with Gemini API: {e}")
        
    except Exception as e:
        logger.error(f"Unexpected error during Jira ticket generation: {e}")
        raise RuntimeError(f"An unexpected error occurred: {e}")

if __name__ == '__main__':
    # Fix stdout encoding for Windows
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    # Test block for local execution
    MOCK_RCA = """
## Executive Summary
The payment service experienced a cascading failure due to database connection exhaustion.

## Timeline
- 08:15:22: Batch transaction started [Log Line 4]
- 08:17:01: DB connection timeout [Log Line 8]

## Root Cause
A stuck analytics query locked the user_ledger table [Log Line 29], causing connection pool exhaustion [Log Line 6].

## Action Items
1. Implement a hard timeout for all analytics batch queries.
2. Add a PagerDuty alert when DB connection pool utilization exceeds 80%.
3. Review and optimize the indexing on the `user_ledger` table to prevent deadlocks.
"""
    try:
        print("--- INITIATING JIRA SKILL TEST ---")
        df = generate_jira_tickets(MOCK_RCA)
        print("\nGenerated Jira Tickets:")
        print(df.to_markdown(index=False))
        
        # Test CSV Export capability
        csv_data = df.to_csv(index=False)
        print("\nCSV Export Preview:")
        print(csv_data)
        
    except Exception as e:
        logger.error(f"Test run failed: {e}")
