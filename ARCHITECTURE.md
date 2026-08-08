# Architecture: Incident RCA Agent

The Incident RCA Agent is built using a modular architecture that separates the frontend UI, core AI reasoning (Agent), and deterministic data extraction (Skill).

## System Components

1. **Frontend (Streamlit UI) -> `ui.py`**
   - Handles file uploads (log ingestion).
   - Manages state (session state for logs, reports, and feedback).
   - Renders the streaming AI response to provide real-time feedback.
   - Provides the human-in-the-loop interface for reviewing and revising the report.

2. **Core AI Brain (RCA Agent) -> `rca_agent.py`**
   - Interfaces with the Google Gemini API (via the `google-genai` SDK).
   - **Pipeline Stage 1:** Streams the narrative RCA report (Executive Summary, Timeline, Root Cause) to the frontend. Employs strict prompt engineering to enforce citations (`[Log Line X]`).
   - **Pipeline Stage 2:** Makes a secondary, blocking API call to generate structured JSON action items based on the narrative.
   - Implements robust error handling and automatic retries with exponential backoff using the `tenacity` library to handle rate limits (429) and server errors (503).

3. **Deterministic Extraction (Jira Skill) -> `jira_skill.py`**
   - Parses the Markdown output from the RCA Agent to extract the embedded JSON block.
   - Validates the schema of the extracted action items (Title, Description, Priority, Assignee).
   - Converts the structured data into a Pandas DataFrame for easy CSV export, ready for Jira bulk import.

## Data Flow
1. User uploads log files via `ui.py`.
2. Logs are concatenated and numbered, then passed to `rca_agent.py`.
3. `rca_agent.py` queries Gemini and streams the narrative report back to `ui.py`.
4. `rca_agent.py` fetches structured action items and appends them to the report.
5. User reviews the report. If revisions are requested, the process loops back to step 3 with the feedback included.
6. Upon approval, `jira_skill.py` extracts the JSON action items.
7. User downloads the action items as a CSV file for Jira.

## Testing Strategy
- **Unit Tests:** `pytest` is used to test individual components (`test_rca_agent.py`, `test_jira_skill.py`).
- **Mocking:** The Google Gemini API is fully mocked during testing to ensure zero quota consumption and fast, deterministic execution in CI/CD.
