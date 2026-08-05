"""
rca_agent.py

The Core Brain of the Incident RCA Agent.
Handles interaction with the Google Gemini API to analyze system logs,
generate structured Root Cause Analysis (RCA) reports, and process human revisions.
Includes robust retry logic for API reliability.
"""

import os
import logging
from typing import Optional
from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from google.api_core.exceptions import TooManyRequests, ServiceUnavailable
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, RetryError

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

class APICallFailedError(Exception):
    """Custom exception raised when the LLM API call fails after all retry attempts."""
    pass

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

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((TooManyRequests, ServiceUnavailable)),
    reraise=True
)
def _execute_llm_call(model: genai.GenerativeModel, prompt: str) -> str:
    """
    Internal helper function to execute the LLM API call with Tenacity retry logic.
    
    Args:
        model (genai.GenerativeModel): The initialized Gemini model.
        prompt (str): The fully constructed prompt to send to the LLM.
        
    Returns:
        str: The raw text response from the LLM.
        
    Raises:
        TooManyRequests: If the API returns a 429 error (retried up to 3 times).
        ServiceUnavailable: If the API returns a 503 error (retried up to 3 times).
        google_exceptions.GoogleAPIError: For any other non-retryable Google API errors.
    """
    logger.info("Executing LLM API call...")
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0.2, # Low temperature for factual, deterministic output
            # No max_output_tokens cap — allows full reports for large log files
        )
    )
    return response.text

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
        APICallFailedError: If the LLM API call fails after all retries or encounters a fatal error.
    """
    if not log_text or not log_text.strip():
        raise ValueError("Log text cannot be empty.")

    # Preprocess logs: Add explicit line numbers to ensure 100% accurate citations
    lines = log_text.strip().split('\n')
    numbered_logs = "\n".join([f"Line {i+1}: {line}" for i, line in enumerate(lines)])

    # Construct the final prompt based on whether this is an initial run or a revision
    if user_feedback:
        logger.info("Preparing revised RCA prompt based on human feedback.")
        full_prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"{REVISION_INSTRUCTION.format(feedback=user_feedback)}\n\n"
            f"ORIGINAL LOGS:\n{numbered_logs}"
        )
    else:
        logger.info("Preparing initial RCA prompt.")
        full_prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"LOGS TO ANALYZE:\n{numbered_logs}"
        )

    try:
        # Initialize the model (using gemini-3.5-flash for speed and cost-efficiency)
        model = genai.GenerativeModel('gemini-3.5-flash')
        
        # Execute the call with automatic retries for 429 and 503 errors
        return _execute_llm_call(model, full_prompt)

    except RetryError as e:
        logger.error(f"API call failed after multiple retries: {e}")
        raise APICallFailedError(
            "The AI service is currently experiencing high traffic or is temporarily unavailable. "
            "Please wait a moment and try again."
        ) from e
        
    except google_exceptions.GoogleAPIError as e:
        logger.error(f"Google API Error during RCA generation: {e}")
        raise APICallFailedError(f"Failed to communicate with the AI service: {e}") from e
        
    except Exception as e:
        logger.error(f"Unexpected error during RCA generation: {e}")
        raise APICallFailedError(f"An unexpected system error occurred: {e}") from e

if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    # Test block for local execution
    try:
        # Attempt to read the massive log file first, fallback to standard mock_logs.txt
        log_file = 'massive_mock_logs.txt' if os.path.exists('massive_mock_logs.txt') else 'mock_logs.txt'
        
        with open(log_file, 'r', encoding='utf-8') as f:
            mock_logs = f.read()
        
        print(f"--- INITIATING TEST RUN WITH {log_file} ---")
        
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
        logger.error("Log file not found. Please ensure mock_logs.txt or massive_mock_logs.txt exists.")
    except APICallFailedError as e:
        logger.error(f"Test run failed due to API error: {e}")
    except Exception as e:
        logger.error(f"Test run failed: {e}")
