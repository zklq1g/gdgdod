"""
rca_agent.py

The Core Brain of the Incident RCA Agent.
Handles interaction with the Google Gemini API to analyze system logs,
generate structured Root Cause Analysis (RCA) reports, and process human revisions.
Supports streaming responses for real-time UI rendering.
"""

import os
import logging
from typing import Optional, Generator
from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from google.api_core.exceptions import TooManyRequests, ServiceUnavailable, ResourceExhausted
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, RetryError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Strict Environment Variable Check
API_KEY = os.environ.get("GOOGLE_API_KEY")
if not API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in environment")

genai.configure(api_key=API_KEY)

class APICallFailedError(Exception):
    """Custom exception raised when the LLM API call fails after all retry attempts."""
    pass

# Define the primary system prompt enforcing strict citations and JSON structure
SYSTEM_PROMPT = """You are an Expert Site Reliability Engineer (SRE) and Root Cause Analysis (RCA) Specialist. Analyze the provided system logs and generate a comprehensive, blameless Root Cause Analysis report.

Use EXACTLY these Markdown headers and no others:
## Executive Summary
## Timeline
## Root Cause
## Action Items

CRITICAL RULE 1 - CITATIONS (ZERO HALLUCINATION):
In "Timeline" and "Root Cause", every claim MUST include a citation referencing the exact log line (e.g., `[Log Line 14]`). If you cannot find direct log evidence, write `[Evidence Not Found]`. Never guess or hallucinate.

CRITICAL RULE 2 - ACTION ITEMS JSON FORMAT:
"## Action Items" MUST be a valid JSON array placed at the very end of your response, wrapped in a markdown code block exactly like this:
```json
[
  {
    "Title": "Concise task summary",
    "Description": "Detailed explanation of what needs to be done and why.",
    "Priority": "High",
    "Assignee": "Role (e.g., Backend Eng, DevOps, DBA)"
  }
]
```
Priority must be exactly "High", "Medium", or "Low". Output nothing after the closing ```.
"""

REVISION_INSTRUCTION = """
The human engineer has reviewed your previous RCA report and provided the following feedback. 
Please regenerate the ENTIRE report, incorporating this feedback while strictly maintaining the Markdown structure, the CRITICAL RULE 1 for citations, and CRITICAL RULE 2 for the JSON Action Items format.

Human Feedback:
{feedback}
"""

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((TooManyRequests, ServiceUnavailable, ResourceExhausted)),
    reraise=True
)
def _initiate_stream(model: genai.GenerativeModel, prompt: str):
    """
    Internal helper function to execute the LLM API call with Tenacity retry logic.
    Note: Retries only apply to the initial connection request (e.g., 429/503). 
    Mid-stream drops are not retried to prevent partial context duplication.
    """
    logger.info("Initiating streaming LLM API call...")
    return model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0.2,
            # No max_output_tokens cap — allows full reports without truncation
        ),
        stream=True
    )

def analyze_incident(log_text: str, user_feedback: Optional[str] = None) -> Generator[str, None, None]:
    """
    Analyzes system logs using the Gemini LLM to generate or revise an RCA report.
    Returns a generator that yields text chunks for streaming.
    """
    if not log_text or not log_text.strip():
        raise ValueError("Log text cannot be empty.")

    # Preprocess logs: Add explicit line numbers to ensure 100% accurate citations
    lines = log_text.strip().split('\n')
    numbered_logs = "\n".join([f"Line {i+1}: {line}" for i, line in enumerate(lines)])

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
        model = genai.GenerativeModel('gemini-3.5-flash')
        response_stream = _initiate_stream(model, full_prompt)
        
        for chunk in response_stream:
            if chunk.text:
                yield chunk.text

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
    try:
        log_file = 'massive_mock_logs.txt' if os.path.exists('massive_mock_logs.txt') else 'mock_logs.txt'
        with open(log_file, 'r', encoding='utf-8') as f:
            mock_logs = f.read()

        print(f"--- INITIATING TEST RUN WITH {log_file} ---")

        response_gen = analyze_incident(log_text=mock_logs)
        rca_report = "".join(list(response_gen))
        with open('rca_report.md', 'w', encoding='utf-8') as f:
            f.write(rca_report)
        print("\n--- INITIAL RCA REPORT GENERATED: rca_report.md ---")

        print("\n--- INITIATING REVISION TEST ---")
        feedback = "The timeline is good, but in the Action Items, please specifically mention adding an alert for DB connection pool utilization exceeding 80%."
        response_gen_rev = analyze_incident(log_text=mock_logs, user_feedback=feedback)
        revised_report = "".join(list(response_gen_rev))
        with open('rca_report_revised.md', 'w', encoding='utf-8') as f:
            f.write(revised_report)
        print("\n--- REVISED RCA REPORT GENERATED: rca_report_revised.md ---")

    except FileNotFoundError:
        logger.error("Log file not found. Please ensure mock_logs.txt or massive_mock_logs.txt exists.")
    except APICallFailedError as e:
        logger.error(f"Test run failed due to API error: {e}")
    except Exception as e:
        logger.error(f"Test run failed: {e}")
