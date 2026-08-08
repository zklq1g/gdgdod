# Agent Documentation: Incident RCA Ecosystem

This repository utilizes an agentic architecture to automate incident response workflows. Rather than treating the LLM as a simple text-in/text-out generator, we have structured the solution into distinct **Agents** and **Skills** to ensure reliability, traceability, and deterministic outputs.

## Architecture Philosophy

- **Specialization**: Agents handle probabilistic reasoning (summarizing chaotic logs, finding patterns). Skills handle deterministic execution (schema validation, CSV formatting).
- **Zero Hallucination**: The AI is restricted by strict system prompts to never infer data without explicit log citations.
- **Resilience**: The agentic layer operates behind a leaky-bucket rate limiter and a SHA-256 caching layer to prevent API exhaustion and ensure consistent outputs.

For a detailed breakdown of the specific agent parameters and deterministic skills, see [AGENTS_AND_SKILLS.md](AGENTS_AND_SKILLS.md).
