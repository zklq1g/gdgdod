"""
rca_agent.py

The Core Brain of the Incident RCA Agent.
Handles interaction with the Google Gemini API to analyze system logs,
generate structured Root Cause Analysis (RCA) reports, and process human revisions.
"""

import os
import logging
from typing import Optional
from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize Google Generative AI Client
API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise EnvironmentError("GOOGLE_API_KEY is not set in the environment or .env file.")
genai.configure(api_key=API_KEY)

# Define the primary system prompt enforcing strict citations and structure
SYSTEM_PROMPT = """You are an Expert Site Reliability Engineer (SRE) and Root Cause Analysis (RCA) Specialist. 
Your task is to analyze the provided system logs and generate a comprehensive, blameless Root Cause Analysis report.

You MUST format your response using EXACTLY the following Markdown headers:
## Executive Summary
## Timeline
## Root Cause
## Action Items

CRITICAL RULE - STRICT CITATIONS & TRACEABILITY (ZERO HALLUCINATION):
In the "Timeline" and "Root Cause" sections, for EVERY single claim, event, or deduction you make, you MUST append a citation in brackets referencing the exact line number from the provided logs (e.g., `[Log Line 14]`). 
If you make a claim but cannot find direct evidence in the logs to support it, you MUST output `[Evidence Not Found]` instead of guessing. Do not hallucinate information outside the provided logs.

Ensure the "Action Items" section contains clear, actionable tasks to prevent recurrence, formatted as a list.
"""

REVISION_INSTRUCTION = """
The human engineer has reviewed your previous RCA report and provided the following feedback. 
Please regenerate the ENTIRE report, incorporating this feedback while strictly maintaining the Markdown structure and the CRITICAL RULE for citations ([Log Line X] or [Evidence Not Found]).

Human Feedback:
{feedback}
"""

def analyze_incident(log_text: str, user_feedback: Optional[str] = None) -> str:
    """
    Analyzes system logs using the Gemini LLM to generate or revise an RCA report.

    Args:
        log_text (str): The raw text of the system logs.
        user_feedback (Optional[str]): Optional feedback from a human engineer for revision.

    Returns:
        str: The generated or revised Markdown RCA report.
        
    Raises:
        ValueError: If the log_text is empty.
        RuntimeError: If the LLM API call fails.
    """
    if not log_text or not log_text.strip():
        raise ValueError("Log text cannot be empty.")

    # Preprocess logs: Add explicit line numbers to ensure 100% accurate citations
    lines = log_text.strip().split('\n')
    numbered_logs = "\n".join([f"Line {i+1}: {line}" for i, line in enumerate(lines)])

    # Construct the final prompt based on whether this is an initial run or a revision
    if user_feedback:
        logger.info("Generating revised RCA report based on human feedback.")
        full_prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"{REVISION_INSTRUCTION.format(feedback=user_feedback)}\n\n"
            f"ORIGINAL LOGS:\n{numbered_logs}"
        )
    else:
        logger.info("Generating initial RCA report.")
        full_prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"LOGS TO ANALYZE:\n{numbered_logs}"
        )

    try:
        # Initialize the model (using gemini-3.5-flash for speed and cost-efficiency)
        model = genai.GenerativeModel('gemini-3.5-flash')
        
        # Generate content with safety settings relaxed slightly to allow analysis of "fatal" errors
        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2, # Low temperature for factual, deterministic output
            )
        )
        
        return response.text

    except google_exceptions.GoogleAPIError as e:
        logger.error(f"Google API Error during RCA generation: {e}")
        raise RuntimeError(f"Failed to communicate with Gemini API: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during RCA generation: {e}")
        raise RuntimeError(f"An unexpected error occurred: {e}")

if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    # Test block for local execution
    try:
        with open('mock_logs.txt', 'r', encoding='utf-8') as f:
            mock_logs = f.read()
        
        print("--- INITIATING TEST RUN ---")
        print("Analyzing mock_logs.txt...")
        
        # Test 1: Initial Analysis
        rca_report = analyze_incident(log_text=mock_logs)
        with open('rca_report.md', 'w', encoding='utf-8') as f:
            f.write(rca_report)
        print("\n--- INITIAL RCA REPORT GENERATED: rca_report.md ---")
        
        # Test 2: Revision Cycle
        print("\n--- INITIATING REVISION TEST ---")
        feedback = "The timeline is good, but in the Action Items, please specifically mention adding an alert for DB connection pool utilization exceeding 80%."
        revised_report = analyze_incident(log_text=mock_logs, user_feedback=feedback)
        with open('rca_report_revised.md', 'w', encoding='utf-8') as f:
            f.write(revised_report)
        print("\n--- REVISED RCA REPORT GENERATED: rca_report_revised.md ---")
        
    except FileNotFoundError:
        logger.error("mock_logs.txt not found. Please ensure it exists in the current directory.")
    except Exception as e:
        logger.error(f"Test run failed: {e}")
