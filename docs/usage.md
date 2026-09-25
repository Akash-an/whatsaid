# Whatsaid Usage Guide

`whatsaid` is a command-line tool and web application for extracting, parsing, and visualizing resources from WhatsApp chat exports. 

This guide focuses on the CLI commands used for managing chats, importing data, and exporting information.

## Setup Instructions

### Backend (Python CLI & API)

The backend is built in Python and manages the CLI parsing as well as the FastAPI server.

1. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. **Install the project and its dependencies:**
   ```bash
   pip install -e .
   ```
   *This makes the `whatsaid` and `whatsaid-api` commands available globally within the virtual environment.*

### Frontend (React UI)

The frontend is a React application built with Vite, located in the `ui/` folder.

1. **Navigate to the frontend directory:**
   ```bash
   cd ui
   ```
2. **Install Node.js dependencies:**
   ```bash
   npm install
   ```
3. **Return to the root directory:**
   ```bash
   cd ..
   ```
## Getting Started

Before using the CLI, ensure you have your WhatsApp chat exported as either a `.txt` file or a `.zip` archive (which can contain media).

To activate the virtual environment and make the CLI available, run:
```bash
source .venv/bin/activate
```

Alternatively, you can run the commands using `python -m whatsaid` or `./.venv/bin/python -m whatsaid`.

## Folder Structure

When you import a chat, the system creates an organized folder structure for it inside the top-level `resources/` directory:

```
resources/
└── <ChatName>/
    ├── _chat.txt                 # The extracted text log
    ├── <media_files>...          # Any images/videos from the .zip
    ├── your_export.zip           # A copy of the original zip you provided
    └── Extracted_Resources.xlsx  # The final parsed resources spreadsheet
```

## CLI Commands

### 1. Import or Append a Chat (`run`)

The `run` command parses your WhatsApp export, stores the messages in the database, extracts links/resources, and generates an Excel spreadsheet.

```bash
whatsaid run <path/to/chat.zip> [options]
```

**Examples:**

- **Interactive Import:**
  ```bash
  whatsaid run ~/Downloads/WhatsApp_Chat.zip
  ```
  *The CLI will prompt you to provide a name for the chat or select an existing one to append messages.*

- **Automated Import (No prompts):**
  ```bash
  whatsaid run ~/Downloads/WhatsApp_Chat.zip --chat "Family Group" --yes
  ```

**Options:**
- `--chat <NAME>`: Supply the chat name directly, skipping the interactive prompt.
- `--out <FILE>`: Override the output Excel filename (defaults to `Extracted_Resources.xlsx`).
- `--db <PATH>`: Path to the SQLite database (defaults to `data/resources.db`).
- `--yes`, `-y`: Automatically skip confirmation prompts.

---

### 2. List All Chats (`chats`)

Shows a formatted table of all imported chats in your database, including their IDs, message counts, and last import dates.

```bash
whatsaid chats
```

**Options:**
- `--db <PATH>`: Custom SQLite database path.

---

### 3. Rename a Chat (`rename-chat`)

Changes the name of an existing chat.

```bash
whatsaid rename-chat <old_name> <new_name>
```

**Example:**
```bash
whatsaid rename-chat "Family Group" "The Family"
```

---

### 4. Delete a Chat (`delete-chat`)

Permanently deletes a chat and all its associated messages and resources from the database. (Note: it does not delete the files in the `resources/` directory).

```bash
whatsaid delete-chat <name> [options]
```

**Example:**
```bash
whatsaid delete-chat "Old Group" --yes
```

**Options:**
- `--yes`, `-y`: Skip the deletion confirmation prompt.

---

### 5. Re-Export Excel (`export`)

If you want to regenerate the Excel file containing the extracted resources without having to parse the original WhatsApp export again, use the `export` command.

```bash
whatsaid export [options]
```

**Example:**
```bash
whatsaid export --chat "The Family"
```
*This places the regenerated `Extracted_Resources.xlsx` inside `resources/The Family/`.*

**Options:**
- `--chat <NAME>`: Generate the export specifically for this chat.
- `--out <FILE>`: Override the output Excel filename.

## Web Application

The `whatsaid` project also includes a FastAPI backend and a React (Vite) frontend for visualizing your extracted resources.

To safely launch both the API and the UI concurrently, use the helper script from the root directory:

```bash
./start.sh
```

- **Backend API:** Available at `http://localhost:8000`
- **Frontend UI:** Available at `http://localhost:5173`
