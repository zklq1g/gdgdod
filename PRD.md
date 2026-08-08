# Product Requirements Document (PRD): Incident RCA Agent

## Problem Statement

When critical system incidents occur, DevOps engineers and SREs spend hours manually sifting through thousands of lines of chaotic, unstructured logs to determine the root cause. This manual process is slow, error-prone, and delays the implementation of preventative measures, leading to longer MTTR (Mean Time To Recovery).

## Target User

- **DevOps Engineers**
- **Site Reliability Engineers (SREs)**
- **Incident Commanders**

## Core Features

1. **Multi-File Log Ingestion**: Ability to ingest massive, multi-file system logs simultaneously (e.g., from API gateways, databases, applications). Files are concatenated with clear separators before analysis.

2. **Citation Enforcement (Zero Hallucination)**: The AI must strictly cite exact log line numbers (e.g., `[Log Line 123]`) for every claim it makes in the analysis. If no evidence exists in the logs, it must output `[Evidence Not Found]` rather than infer.

3. **Human-in-the-Loop Revision**: Engineers can review the generated Root Cause Analysis (RCA) report, provide natural language feedback, and request targeted revisions before finalizing. No action item is ever exported without explicit engineer approval.

4. **Jira Integration (Adapter Pattern)**: Deterministic extraction of actionable tasks from the RCA report into structured JSON, exposed via two paths:
   - **Direct Push**: Simulates an Atlassian API call and returns realistic `ENG-XXXX` ticket IDs with clickable hyperlinks.
   - **CSV Bulk Import**: Generates a formatted CSV file optimized for Jira's Bulk Issue Import tool.
   - The adapter pattern allows future swapping to Linear, GitHub Issues, or ServiceNow without modifying the core agent.

5. **Resilient API Handling**: The system must handle API rate limits (429) and server errors (503) transparently via exponential backoff retries, without surfacing errors to the user unless all retries are exhausted.

6. **Deterministic Caching**: SHA-256 hashing of log inputs ensures identical requests return instantly from cache, saving API quota and reducing latency.

## Success Metrics

- **Performance**: Process up to 100,000 characters of log data and return the first streaming token in under 5 seconds.
- **Accuracy**: Achieve 0% hallucination rate on log line citations via deterministic LLM prompting.
- **Actionability**: Generate at least one high-priority Jira-ready ticket for every analyzed incident.
- **Reliability**: Zero unhandled crashes during the human-in-the-loop approval and export flow.
