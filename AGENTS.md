# AI Agent Guidelines (AGENTS.md)

This document establishes the core directives, conventions, and operational rules for all AI co-pilots and autonomous agents interacting with this repository.

## 1. Core Directives
- **Documentation First:** All implementations must update or create relevant documentation (READMEs, inline comments, docstrings) in sync with code changes.
- **Test-Driven Development (TDD):** We strictly follow TDD. Before writing functional code, write failing tests that define the expected behavior. Then, write the minimal code to pass the tests, and refactor.
- **Think Before You Act:** Always plan out your approach. Read existing context carefully to avoid duplicating code or breaking existing patterns.
- **Scope Containment:** Make minimal, focused changes. Do not reformat or modify code unrelated to the explicit user request or task at hand.

## 2. Coding Standards
- **Clarity over Cleverness:** Write code that is readable and easily maintainable by both humans and AI.
- **Robust Error Handling:** Ensure all edge cases are considered. Fail gracefully and log errors appropriately.
- **Modularity:** Keep functions and classes small, focused on a single responsibility, and highly testable.
- **Type Safety:** Use strong typing (e.g., Python type hints, TypeScript) and define clear interfaces where applicable.

## 3. Standard Workflow
1. **Understand & Clarify:** Review the objective. Ask the user clarifying questions if the requirements are ambiguous.
2. **Context Gathering:** Read relevant source files, existing tests, and documentation.
3. **Write Tests:** Draft comprehensive tests for the expected behavior.
4. **Implementation:** Write the functional code to satisfy the tests.
5. **Verification:** Run the tests to ensure they pass without introducing regressions.
6. **Documentation & Cleanup:** Update any `.md` files or inline docs.

## 4. Communication Protocol
- Always summarize the actions taken concisely.
- Highlight any blocking issues or design decisions that require human input.
- Use clean, GitHub-flavored markdown to format responses, including code blocks and clickable file paths.

## 5. Project Structure Overview
This repository follows a decoupled architecture separating the backend data pipeline from the frontend visualization UI.

- **`src/whatsaid/`**: The core Python package. Contains the chat extraction logic and the FastAPI backend (`src/whatsaid/api/`).
- **`ui/`**: The React/Vite frontend application that visualizes the chat data.
- **`docs/`**: Contains architectural guidelines, database schemas, and UI design documents.
- **`data/` & `resources/`**: Storage directories for raw WhatsApp chat exports and auxiliary files.
- **`resources.db`**: The local SQLite database where parsed chat data is persisted.

## 6. Local Development Environment
- **Running the App (`start.sh`):** A helper script `./start.sh` is provided in the project root. It safely finds and kills any dangling processes on ports 8000 and 5173, activates the Python virtual environment, and spins up both the FastAPI backend and Vite frontend concurrently. Agents should recommend this script for starting the application.
- **Backend:** Accessible at `http://localhost:8000`. Dependencies and entry points are managed via `pyproject.toml`.
- **Frontend:** Accessible at `http://localhost:5173`. Managed via `ui/package.json` (running strictly on port 5173 to ensure consistent restarts).
