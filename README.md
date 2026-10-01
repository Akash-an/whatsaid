# Whatsaid

Whatsaid is a full-stack application that parses, processes, and visualizes WhatsApp chat exports. It features a decoupled architecture with a Python/FastAPI backend for data extraction and processing, and a React/Vite frontend for visualizing the chat data.

## Project Structure

- **`src/whatsaid/`**: The core Python package. Contains the chat extraction logic and the FastAPI backend (`src/whatsaid/api/`).
- **`ui/`**: The React/Vite frontend application that visualizes the chat data.
- **`docs/`**: Contains architectural guidelines, database schemas, and UI design documents.
- **`data/` & `resources/`**: Storage directories for raw WhatsApp chat exports and auxiliary files.
- **`data/resources.db`**: The local SQLite database where parsed chat data is persisted.
- **`scripts/`**: Helper scripts, including `start.sh` to run the application.

## Prerequisites

- **Python** (Virtual environment configured in `.venv`)
- **Node.js** and **npm** (for the UI)

## Running the Application

A helper script is provided to safely handle environment setup and start both the backend and frontend concurrently. 

You can run the application with:

```bash
./scripts/start.sh
```

This script will:
1. Kill any dangling processes on ports 8000 and 5173.
2. Activate the Python virtual environment and start the FastAPI backend (accessible at `http://localhost:8000`).
3. Start the Vite React frontend (accessible at `http://localhost:5173`).

## Development Guidelines

Please refer to [`AGENTS.md`](AGENTS.md) for detailed instructions on:
- Core Directives and Test-Driven Development (TDD)
- Coding Standards (Type safety, Modularity, Error handling)
- AI Agent Communication Protocols
