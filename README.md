# Incident RCA Agent

An AI-powered Developer Productivity Tool that ingests chaotic system logs, performs blameless Root Cause Analysis (RCA) with strict traceability, and exports actionable Jira tickets.

## Requirements

- **Python 3.11+**
- A Google Gemini API Key ([Get one here](https://aistudio.google.com/app/apikey))

## Quick Start

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd incident-rca-agent
   ```

2. **Set up a virtual environment & install dependencies**
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**
   Create a `.env` file in the root directory and add your API key:
   ```env
   GOOGLE_API_KEY=your_actual_api_key_here
   ```

4. **Run the Application**
   ```bash
   streamlit run ui.py
   ```

## Architecture

The application is built with a modular, strictly-typed Python backend and a Streamlit frontend.

- **`ui.py`**: The Streamlit frontend. Handles multi-file log ingestion, streaming UI rendering, and the human-in-the-loop approval workflow.
- **`rca_agent.py`**: The core AI brain. Manages prompt engineering, strict citation enforcement (`[Log Line X]`), and API reliability via `tenacity` exponential backoff.
- **`jira_skill.py`**: A deterministic parsing skill. Extracts structured JSON action items from the LLM's Markdown output and converts them into a Pandas DataFrame for CSV export.
- **`test_*.py`**: Comprehensive `pytest` suites utilizing `unittest.mock` to ensure 100% offline CI/CD execution without consuming API quota.

## Key Features

- **Zero Hallucination Citations**: The LLM is strictly bound to reference exact log line numbers for every claim.
- **Human-in-the-Loop**: Engineers can review, request targeted revisions, and approve reports before ticket generation.
- **Resilient API Handling**: Automatic retries with exponential backoff for 429 and 503 HTTP errors.
- **Streaming Output**: Real-time token rendering for immediate feedback on large log files.
