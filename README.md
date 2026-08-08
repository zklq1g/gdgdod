#  Incident RCA Agent

An AI-powered Developer Productivity Tool that ingests chaotic system logs, performs blameless Root Cause Analysis (RCA) with strict traceability, and exports actionable Jira tickets.

##  Demo Video
[Link to Demo Video (Placeholder)](#)

##  Quick Start

Follow these exact steps to install and run the application locally.

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd incident-rca-agent
   ```

2. **Configure Environment Variables**
   Create a `.env` file in the root directory and add your Google Gemini API key:
   ```env
   GOOGLE_API_KEY=your_actual_api_key_here
   ```

3. **Run the Application** (Auto-Setup)
   We have provided automated scripts that will instantly create a virtual environment, install dependencies, and launch the UI. (Python 3.10+ required).
   
   **On Windows:**
   Double-click `run.bat` or run it from the terminal:
   ```cmd
   run.bat
   ```
   
   **On macOS/Linux:**
   ```bash
   bash run.sh
   ```

4. **How to Use**
   - Upload a `.txt` log file (e.g., `mock_logs.txt`).
   - Click **Generate RCA Report**.
   - Review the AI-generated report. If needed, type feedback in the revision box to request changes.
   - Click **Approve Report** to finalize.
   - You can now push directly to the mocked Jira board or download the `jira_tickets.csv` for bulk import.

5. **Run the Tests**
   Ensure dependencies are installed, then run:
   ```bash
   pytest tests/ -v
   ```

##  Architecture

The application is built with a modular, strictly-typed Python backend and a Streamlit frontend. It enforces zero-hallucination citations and human-in-the-loop workflows.

For a detailed breakdown of the system components, data flow, and testing strategy, please read our [Architecture Documentation](ARCHITECTURE.md).

##  Key Features

- **Zero Hallucination Citations**: The LLM is strictly bound to reference exact log line numbers for every claim.
- **Human-in-the-Loop**: Engineers can review, request targeted revisions, and approve reports before ticket generation.
- **Resilient API Handling**: Automatic retries with exponential backoff for HTTP errors.
- **Jira Export**: Generates a formatted CSV file optimized for Jira's Bulk Issue Import tool based on actionable tasks.
