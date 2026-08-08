# Architecture: Incident RCA Agent

The Incident RCA Agent is built using a modular architecture that separates the frontend UI, core AI reasoning (Agent), and deterministic data extraction (Skill).

## System Components

1. **Frontend (Streamlit UI) -> `ui.py`**
   - Handles multi-file log ingestion and concatenation.
   - Manages a strict state machine (`idle -> uploaded -> generated -> revision -> approved`).
   - Renders the streaming AI response token-by-token for real-time feedback.
   - Provides the human-in-the-loop interface for reviewing, revising, and approving reports.
   - Upon approval, instantly parses the Jira DataFrame and presents two side-by-side export options: Direct Push (simulated) and CSV Download.
   - Theme is locked to light mode via `.streamlit/config.toml` for consistent presentation.

2. **Core AI Brain (RCA Agent) -> `rca_agent.py`**
   - Interfaces with the Google Gemini API (via the `google-genai` SDK).
   - **Pipeline Stage 1:** Streams the narrative RCA report (Executive Summary, Timeline, Root Cause) to the frontend. Employs strict prompt engineering to enforce citations (`[Log Line X]`).
   - **Pipeline Stage 2:** Makes a secondary, blocking API call to generate structured JSON action items based on the narrative.
   - Implements a SHA-256 cache layer: identical log inputs return instantly without consuming API quota.
   - Implements robust error handling and automatic retries with exponential backoff using the `tenacity` library to handle rate limits (429) and server errors (503).
   - A leaky-bucket rate limiter caps throughput at 10 RPM to stay within free-tier API limits.

3. **Deterministic Extraction (Jira Skill) -> `jira_skill.py`**
   - Parses the Markdown output from the RCA Agent to extract the embedded JSON block via Regex.
   - Validates the schema of the extracted action items (Title, Description, Priority, Assignee).
   - Converts the structured data into a Pandas DataFrame.
   - Exposes two export paths (adapter pattern): a simulated Direct Jira Push and a CSV bulk import file.

4. **Configuration -> `.streamlit/config.toml`**
   - Enforces light theme globally. Users cannot toggle to dark mode.
   - Sets the primary accent color (`#2563EB`) to match the custom CSS in `ui.py`.

5. **Quick-Start Scripts -> `run.sh` / `run.bat`**
   - Cross-platform automated setup scripts.
   - Auto-detect Python, create a virtual environment, install all dependencies from `requirements.txt`, and launch the Streamlit UI in a single command.

## Data Flow

1. User uploads one or more `.txt` log files via `ui.py`.
2. Logs are concatenated with file headers and passed to `rca_agent.py`.
3. `rca_agent.py` checks the SHA-256 cache. On a miss, it queries Gemini and streams the narrative report back to `ui.py`.
4. `rca_agent.py` makes a secondary call to generate structured JSON action items and appends them to the report.
5. User reviews the report. If revisions are requested, the process loops back to step 3 with the feedback included.
6. Upon approval, `jira_skill.py` is invoked silently to parse the JSON action items into a DataFrame.
7. User chooses to push directly to the Jira simulation or download the CSV for bulk import.

## Deployment

- **Platform**: Streamlit Community Cloud (recommended) or Hugging Face Spaces.
- **Environment Variable**: `GOOGLE_API_KEY` must be set as a secret in the hosting platform's secrets manager (TOML format for Streamlit Cloud: `GOOGLE_API_KEY = "your_key"`).

## Testing Strategy

- **Unit Tests**: `pytest` is used to test individual components (`tests/test_rca_agent.py`, `tests/test_jira_skill.py`).
- **Mocking**: The Google Gemini API is fully mocked during testing to ensure zero quota consumption and fast, deterministic execution in CI/CD.
- **CI/CD**: GitHub Actions (`.github/workflows/ci.yml`) runs the full test suite on every push to `main`.
