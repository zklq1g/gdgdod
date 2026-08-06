"""
rca_agent.py

The Core Brain of the Incident RCA Agent.
Handles interaction with the Google Gemini API to analyze system logs,
generate structured Root Cause Analysis (RCA) reports, and process human revisions.

Architecture: Two-call pipeline.
  Call 1 (streaming): Generates the narrative report (Executive Summary, Timeline, Root Cause).
  Call 2 (blocking):  Generates the structured JSON Action Items from the completed narrative.
This guarantees the JSON block is always produced regardless of log file size.
"""

import os
import logging
from typing import Optional, Generator
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError
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

# Initialize the new SDK client
client = genai.Client(api_key=API_KEY)

class APICallFailedError(Exception):
    """Custom exception raised when the LLM API call fails after all retry attempts."""
    pass

# --- PROMPTS ---

# Call 1: Narrative report (no JSON required — keeps output budget free)
NARRATIVE_PROMPT = """You are an Expert Site Reliability Engineer (SRE) and Root Cause Analysis (RCA) Specialist. Analyze the provided system logs and generate a blameless Root Cause Analysis report.

Use EXACTLY these Markdown headers and no others:
## Executive Summary
## Timeline
## Root Cause

CITATIONS RULE (ZERO HALLUCINATION):
In "Timeline" and "Root Cause", every claim MUST cite the exact log line (e.g., `[Log Line 14]`). If no log evidence exists, write `[Evidence Not Found]`. Never hallucinate.

Be concise. Do not pad sections unnecessarily.
"""

# Call 2: Action items JSON extracted from the narrative
ACTION_ITEMS_PROMPT = """You are an SRE producing Jira tickets from a completed RCA report.

Based on the following RCA report, produce ONLY a JSON array of action items. No other text, no explanation, no markdown prose — output the JSON array only, wrapped in a ```json block.

Schema:
```json
[
  {{
    "Title": "Concise task title",
    "Description": "What must be done and why, referencing the RCA findings.",
    "Priority": "High",
    "Assignee": "Role (e.g., Backend Eng, DevOps, DBA)"
  }}
]
```
Priority must be exactly "High", "Medium", or "Low". Output nothing after the closing ```.

RCA REPORT:
{narrative}
"""

REVISION_INSTRUCTION = """
The human engineer has reviewed your previous RCA report and provided the following feedback.
Regenerate the ENTIRE report (## Executive Summary, ## Timeline, ## Root Cause) incorporating this feedback while maintaining citations.

Human Feedback:
{feedback}
"""

# --- API HELPERS ---

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(APIError),
    reraise=True
)
def _initiate_stream(prompt: str):
    """Initiates a streaming LLM call. Tenacity retries protect the initial connection."""
    logger.info("Initiating streaming LLM API call (narrative)...")
    return client.models.generate_content_stream(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2)
    )

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(APIError),
    reraise=True
)
def _generate_action_items(narrative: str) -> str:
    """Blocking call to generate the JSON action items from the completed narrative."""
    logger.info("Generating structured JSON action items (blocking call)...")
    prompt = ACTION_ITEMS_PROMPT.format(narrative=narrative)
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=1024
        )
    )
    return response.text

# --- PUBLIC API ---

def analyze_incident(log_text: str, user_feedback: Optional[str] = None) -> Generator[str, None, None]:
    """
    Analyzes system logs using a two-call pipeline:
      1. Streams the narrative RCA (Executive Summary, Timeline, Root Cause).
      2. Makes a blocking call to generate the JSON Action Items section.
    Yields text chunks for real-time streaming to the UI.
    """
    if not log_text or not log_text.strip():
        raise ValueError("Log text cannot be empty.")

    # Add explicit line numbers for 100% accurate citations
    lines = log_text.strip().split('\n')
    numbered_logs = "\n".join([f"Line {i+1}: {line}" for i, line in enumerate(lines)])

    if user_feedback:
        logger.info("Preparing revised RCA prompt based on human feedback.")
        narrative_prompt = (
            f"{NARRATIVE_PROMPT}\n\n"
            f"{REVISION_INSTRUCTION.format(feedback=user_feedback)}\n\n"
            f"ORIGINAL LOGS:\n{numbered_logs}"
        )
    else:
        logger.info("Preparing initial RCA prompt.")
        narrative_prompt = (
            f"{NARRATIVE_PROMPT}\n\n"
            f"LOGS TO ANALYZE:\n{numbered_logs}"
        )

    try:
        # --- CALL 1: Stream the narrative ---
        response_stream = _initiate_stream(narrative_prompt)
        narrative_chunks = []

        for chunk in response_stream:
            # Catch mid-stream rate limit errors (Tenacity only protects the initial connection)
            try:
                if chunk.text:
                    narrative_chunks.append(chunk.text)
                    yield chunk.text
            except APIError as e:
                logger.error(f"Stream interrupted mid-response by API error: {e}")
                raise APICallFailedError(
                    "The stream was interrupted by an API error (e.g. rate limit). "
                    "Please wait a moment and try again."
                ) from e

        narrative = "".join(narrative_chunks)
        logger.info(f"Narrative complete. Length: {len(narrative)} chars.")

        # --- CALL 2: Generate structured Action Items (blocking) ---
        yield "\n\n## Action Items\n\n"
        action_items_text = _generate_action_items(narrative)
        yield action_items_text
        logger.info("Action items generated successfully.")

    except RetryError as e:
        logger.error(f"API call failed after multiple retries: {e}")
        raise APICallFailedError(
            "The AI service is currently unavailable after multiple retries. "
            "Please wait a moment and try again."
        ) from e
    except APICallFailedError:
        raise
    except APIError as e:
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

    except FileNotFoundError:
        logger.error("Log file not found. Please ensure mock_logs.txt or massive_mock_logs.txt exists.")
    except APICallFailedError as e:
        logger.error(f"Test run failed due to API error: {e}")
    except Exception as e:
        logger.error(f"Test run failed: {e}")
