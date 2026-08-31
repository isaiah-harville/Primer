# Primer Agent Instructions

## Repository policy

- Do not stage or commit documentation files unless the user explicitly requests it.
- This prohibition includes `docs/`, Superpowers design specifications and implementation plans, README changes, architecture notes, and generated documentation.
- `AGENTS.md` is the sole standing exception and may be maintained as repository policy.
- If a required workflow generates documentation, keep it local and untracked and summarize the actionable result in the conversation.
- Preserve unrelated user changes and do not rewrite shared or pushed history.

## Product direction

- Build a self-hosted, multi-user RAG application for students and researchers.
- Keep libraries private in the MVP, but preserve an authorization model that can support sharing libraries with other users in a future release.
- Let users copy or export assistant responses from chat, including their citations.
- Keep authentication toggleable. Use generic OIDC through `oauth2-proxy`, with Authentik as the initial tested provider; do not implement authentication flows in Primer.
- Support vLLM, Ollama, and llama.cpp through their OpenAI-compatible APIs.
- Use Haystack, Docling, and other established libraries instead of hand-rolling parsing, chunking, embeddings, retrieval adapters, or tool protocols.
- Tools and code execution must be operator-controlled, user-approved, and isolated through ephemeral MCP sandbox providers. Never expose the host shell.
- Select the vector database per deployment and keep it behind Haystack's document-store integrations.

## Technology constraints

- Use Python 3.13 or newer, `uv`, Ruff, Astral `ty`, and pytest for Python services.
- Run Python type checking with `uv run ty check`; do not add mypy or Pyright.
- Use SvelteKit, TypeScript, pnpm, and Biome for the web application.
- Use Alembic for database migrations and never run migrations during normal application startup.
- Target Kubernetes for shared deployments and cross-platform Docker Compose for local single-user deployments.

## GitHub tracking

- Use `gh` to create implementation issues after the implementation plan is approved.
- Use only these priority labels: `priority:high`, `priority:medium`, `priority:low`, and `priority:future`.
- Put post-MVP roadmap work, including library sharing, under `priority:future`.
- Every implementation issue must include scope, dependencies, acceptance criteria, and verification steps.
