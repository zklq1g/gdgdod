"""
jira_skill.py

The Custom Skill for the Incident RCA Agent.
Deterministically parses the JSON-formatted 'Action Items' block from the RCA report
and converts it into a Jira-ready Pandas DataFrame.
Includes robust sanitization for common LLM JSON formatting errors.
"""

import re
import json
import logging
from typing import Optional, List, Dict, Any
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def extract_json_block(rca_markdown: str) -> Optional[str]:
    """
    Extracts the raw JSON string using bracket matching.
    """
    # 1. Standard regex to find ```json ... ```
    pattern = r"```json\s*(.*?)\s*```"
    match = re.search(pattern, rca_markdown, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # 2. Fallback: Find the start of the JSON array. 
    # We specifically look for '[{' (with optional whitespace) to skip over 
    # citation brackets like '[Log Line 3]' in the narrative text.
    match = re.search(r'\[\s*\{', rca_markdown)
    if not match:
        return None
        
    start_idx = match.start()
        
    bracket_count = 0
    in_string = False
    escape_next = False
    
    for i in range(start_idx, len(rca_markdown)):
        char = rca_markdown[i]
        
        if escape_next:
            escape_next = False
            continue
            
        if char == '\\':
            escape_next = True
            continue
            
        if char == '"':
            in_string = not in_string
            continue
            
        if not in_string:
            if char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1
                if bracket_count == 0:
                    return rca_markdown[start_idx:i+1].strip()
                        
    return None

def sanitize_json_string(json_str: str) -> str:
    """
    Cleans common LLM JSON formatting errors that break Python's strict json.loads().
    """
    # Remove trailing commas before closing brackets (e.g., `},]` -> `}]`)
    json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
    
    return json_str

def generate_jira_tickets(rca_markdown: str) -> pd.DataFrame:
    """
    Parses the JSON action items from an RCA report into a Pandas DataFrame.
    """
    expected_columns = ['Title', 'Description', 'Priority', 'Assignee']
    empty_df = pd.DataFrame(columns=expected_columns)

    logger.info("Extracting JSON block from RCA report...")
    json_str = extract_json_block(rca_markdown)
    
    if not json_str:
        logger.warning("No JSON block found in the RCA report.")
        return empty_df

    try:
        # Sanitize the raw JSON string before parsing
        cleaned_json_str = sanitize_json_string(json_str)
        
        logger.info("Parsing sanitized JSON data...")
        # Use strict=False to allow unescaped control characters inside strings
        tickets_data: List[Dict[str, Any]] = json.loads(cleaned_json_str, strict=False)
        
        if not isinstance(tickets_data, list):
            logger.warning("Extracted JSON is not a list. Expected an array of objects.")
            return empty_df

        df = pd.DataFrame(tickets_data)
        
        # Enforce schema: ensure all expected columns exist
        for col in expected_columns:
            if col not in df.columns:
                df[col] = "N/A"
                
        # Filter to only keep expected columns
        df = df[expected_columns]
        
        # Standardize Priority
        df['Priority'] = df['Priority'].apply(
            lambda x: x.capitalize() if str(x).capitalize() in ['High', 'Medium', 'Low'] else 'Medium'
        )
        
        logger.info(f"Successfully parsed {len(df)} Jira tickets.")
        return df

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON even after sanitization: {e}")
        return empty_df
    except Exception as e:
        logger.error(f"Unexpected error processing Jira tickets: {e}")
        return empty_df
