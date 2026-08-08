# Agent Documentation: Incident RCA Ecosystem

This repository utilizes an agentic architecture to automate incident response workflows. Rather than treating the LLM as a simple text-in/text-out generator, we have structured the solution into distinct **Agents** and **Skills** to ensure reliability, traceability, and deterministic outputs.

## Architecture Philosophy

- **Specialization**: Agents handle probabilistic reasoning (summarizing chaotic logs, finding patterns). Skills handle deterministic execution (schema validation, structured data formatting).
- **Zero Hallucination**: The AI is restricted by strict system prompts to never infer data without explicit log citations. Every claim must reference an exact log line number using the format `[Log Line X]`.
- **Resilience**: The agentic layer operates behind a leaky-bucket rate limiter and a SHA-256 caching layer to prevent API exhaustion and ensure consistent, reproducible outputs.
- **Human-in-the-Loop**: No action item is ever exported without an explicit engineer approval step. The agent proposes; the human decides.
- **Adapter Pattern for Integrations**: The Jira export layer is designed as an adapter. The current implementation supports a Direct Push simulation and CSV bulk import. This pattern allows future swapping of targets (Linear, GitHub Issues, ServiceNow) without modifying the core RCA Agent.

For a detailed breakdown of the specific agent parameters and deterministic skills, see [AGENTS_AND_SKILLS.md](AGENTS_AND_SKILLS.md).
