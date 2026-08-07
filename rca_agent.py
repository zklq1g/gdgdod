"""
rca_agent.py

The Core Brain of the Incident RCA Agent.
Updated with Free-Tier Optimizations:
- In-memory caching to prevent burning API quota on identical requests.
- Explicit max_output_tokens to prevent mid-generation cutoffs.
- Request throttling to prevent RPM (Requests Per Minute) rate limits.
"""

import os
import time
import hashlib
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

API_KEY = os.environ.get("GOOGLE_API_KEY")
if not API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in environment")

client = genai.Client(api_key=API_KEY)

class APICallFailedError(Exception):
    pass

# --- FREE TIER OPTIMIZATION: IN-MEMORY CACHE ---
# Prevents burning your daily quota (1500 RPD) when testing the same logs repeatedly.
_API_CACHE = {}

def _get_cache_key(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()

# --- PROMPTS ---

NARRATIVE_PROMPT = """You are an Expert Site Reliability Engineer (SRE) and Root Cause Analysis (RCA) Specialist. Analyze the provided system logs and generate a blameless Root Cause Analysis report.

Use EXACTLY these Markdown headers and no others:
## Executive Summary
## Timeline
## Root Cause

CITATIONS RULE (ZERO HALLUCINATION):
In "Timeline" and "Root Cause", every claim MUST cite the exact log line (e.g., `[Log Line 14]`). If no log evidence exists, write `[Evidence Not Found]`. Never hallucinate.

Be concise. Do not pad sections unnecessarily.
"""

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

CRITICAL JSON FORMATTING RULES:
1. Do not use literal line breaks inside JSON string values. Use the escaped sequence \\n instead.
2. Do not include markdown formatting inside the JSON strings.
3. Ensure all double quotes inside strings are escaped as \\".
4. Output nothing after the closing ```.

Priority must be exactly "High", "Medium", or "Low".

RCA REPORT:
{narrative}
"""

REVISION_INSTRUCTION = """
The human engineer has reviewed your previous RCA report and provided the following feedback.
Regenerate the ENTIRE report incorporating this feedback while maintaining citations.

Human Feedback:
{feedback}
"""

# --- API HELPERS ---

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=10, max=60),
    retry=retry_if_exception_type(APIError),
    reraise=True
)
def _init_stream(prompt: str):
    """Tenacity-protected stream initializer. Retries on 429/503 at connection time."""
    return client.models.generate_content_stream(
        model='gemini-flash-latest',
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=8192
        )
    )

def _generate_narrative_stream(prompt: str) -> Generator[str, None, None]:
    """
    Streaming generator for the narrative report.
    Includes caching and free-tier output limit protections.
    """
    cache_key = _get_cache_key(prompt)

    # 1. Return from cache if available (Saves API Quota!)
    if cache_key in _API_CACHE:
        logger.info("Returning cached narrative stream to save API quota.")
        last_chunk = None
        for chunk in _API_CACHE[cache_key]:
            if chunk.text:
                yield chunk.text
            last_chunk = chunk

        # Check truncation even for cached responses
        if last_chunk and hasattr(last_chunk, 'candidates') and last_chunk.candidates:
            finish_reason = last_chunk.candidates[0].finish_reason
            if finish_reason and 'MAX_TOKENS' in str(finish_reason).upper():
                yield "\n\n---\n**⚠ WARNING: Output Truncated**\nThe report exceeded the free-tier output token limit (8192 tokens) and was cut off. Please upload smaller log files."
        return

    # 2. Fetch from API and cache
    logger.info("Initializing narrative report stream...")
    try:
        stream = _init_stream(prompt)

        chunks_to_cache = []
        last_chunk = None

        for chunk in stream:
            if chunk.text:
                chunks_to_cache.append(chunk)
                yield chunk.text
            last_chunk = chunk

        # Cache the chunks for future identical requests
        _API_CACHE[cache_key] = chunks_to_cache

        # Log token usage
        if last_chunk and hasattr(last_chunk, 'usage_metadata') and last_chunk.usage_metadata:
            usage = last_chunk.usage_metadata
            logger.info(f"Narrative Token Usage - Prompt: {usage.prompt_token_count}, Candidates: {usage.candidates_token_count}, Total: {usage.total_token_count}")

        # Check for truncation (Mid-generation cutoff detection)
        if last_chunk and hasattr(last_chunk, 'candidates') and last_chunk.candidates:
            finish_reason = last_chunk.candidates[0].finish_reason
            if finish_reason and 'MAX_TOKENS' in str(finish_reason).upper():
                yield "\n\n---\n**⚠ WARNING: Output Truncated**\nThe report exceeded the free-tier output token limit (8192 tokens) and was cut off. Please upload smaller log files or split them into multiple analyses."

    except APIError as e:
        logger.error(f"Google API Error during narrative streaming: {e}")
        raise APICallFailedError(f"Failed to communicate with the AI service: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error during narrative streaming: {e}")
        raise APICallFailedError(f"An unexpected system error occurred: {e}") from e

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=10, max=60),
    retry=retry_if_exception_type(APIError),
    reraise=True
)
def _generate_action_items(narrative: str) -> str:
    """Blocking call to generate the JSON action items. Includes caching."""
    cache_key = _get_cache_key(f"action_items_{narrative}")

    # Return from cache if available
    if cache_key in _API_CACHE:
        logger.info("Returning cached action items to save API quota.")
        return _API_CACHE[cache_key]

    logger.info("Generating structured JSON action items (blocking call)...")
    prompt = ACTION_ITEMS_PROMPT.format(narrative=narrative)
    response = client.models.generate_content(
        model='gemini-flash-latest',
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=1024
        )
    )

    # Cache the result
    _API_CACHE[cache_key] = response.text

    if hasattr(response, 'usage_metadata') and response.usage_metadata:
        usage = response.usage_metadata
        logger.info(f"Action Items Token Usage - Prompt: {usage.prompt_token_count}, Candidates: {usage.candidates_token_count}, Total: {usage.total_token_count}")

    return response.text

# --- PUBLIC API ---

def analyze_incident(log_text: str, user_feedback: Optional[str] = None) -> Generator[str, None, None]:
    if not log_text or not log_text.strip():
        raise ValueError("Log text cannot be empty.")

    lines = log_text.strip().split('\n')
    numbered_logs = "\n".join([f"Line {i+1}: {line}" for i, line in enumerate(lines)])

    if user_feedback:
        narrative_prompt = (
            f"{NARRATIVE_PROMPT}\n\n"
            f"{REVISION_INSTRUCTION.format(feedback=user_feedback)}\n\n"
            f"ORIGINAL LOGS:\n{numbered_logs}"
        )
    else:
        narrative_prompt = (
            f"{NARRATIVE_PROMPT}\n\n"
            f"LOGS TO ANALYZE:\n{numbered_logs}"
        )

    try:
        # --- CALL 1: Generate the narrative (streaming) ---
        narrative_chunks = []
        for chunk in _generate_narrative_stream(narrative_prompt):
            narrative_chunks.append(chunk)
            yield chunk

        full_narrative = "".join(narrative_chunks)
        logger.info(f"Narrative stream complete. Length: {len(full_narrative)} chars.")

        # --- CALL 2: Generate structured Action Items (blocking) ---
        yield "\n\n## Action Items\n\n"

        # FREE TIER FIX: Small delay to prevent hitting the 15 RPM limit
        time.sleep(2)

        action_items_text = _generate_action_items(full_narrative)
        yield action_items_text
        logger.info("Action items generated successfully.")

    except RetryError as e:
        logger.error(f"API call failed after multiple retries: {e}")
        raise APICallFailedError("The AI service is currently unavailable after multiple retries.") from e
    except APICallFailedError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during RCA generation: {e}")
        raise APICallFailedError(f"An unexpected system error occurred: {e}") from e

# --- REGENERATE ACTION ITEMS FALLBACK ---
def regenerate_action_items(rca_report: str) -> str:
    """
    Regenerates ONLY the Action Items JSON from an existing RCA report.
    """
    logger.info("Regenerating action items from existing report...")
    return _generate_action_items(rca_report)


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

    except Exception as e:
        logger.error(f"Test run failed: {e}")


