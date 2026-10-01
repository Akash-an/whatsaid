# Whatsaid Web UI - Design Document

## 1. Overview & Goals
The current `whatsaid` application extracts WhatsApp chat information into a local SQLite database (`data/resources.db`) and exports it to an Excel spreadsheet. The goal of this project is to build a rich, interactive Web UI for data visualization, allowing users to deeply explore, filter, and review the extracted data without relying on static spreadsheets.

The Web UI will focus on visually engaging dashboards, interactive data tables for resource review, and deep insights into chatting patterns and extracted links.

## 2. Technology Stack
*   **Backend (API Server):** **FastAPI** (Python). Since the core application is already in Python, FastAPI provides a lightweight, high-performance way to serve the SQLite data via REST endpoints.
*   **Frontend Framework:** **React (via Vite)**. Provides a fast development environment and robust component model.
*   **Styling:** **Vanilla CSS** with CSS Variables (Custom Properties). Adhering to modern design principles, utilizing smooth gradients, glassmorphism, and avoiding heavy generic frameworks to maintain a premium, bespoke aesthetic.
*   **Data Visualization:** **Recharts** or **Chart.js**. For rendering responsive and dynamic charts (pie charts, bar charts, time-series).
*   **Typography:** **Inter** or **Outfit** (Google Fonts) for a sleek, modern look.

## 3. UI/UX Design Aesthetics
The interface will be designed to feel **premium and state-of-the-art**:
*   **Color Palette:** A sleek dark mode by default (e.g., deep charcoal `#0F172A` with vibrant accent colors like neon purple `#8B5CF6` and cyan `#06B6D4`).
*   **Glassmorphism:** Use of backdrop filters (`backdrop-filter: blur(10px)`) on cards and navigation elements to create depth.
*   **Micro-animations:** Subtle hover states, smooth page transitions, and staggered list loading animations to make the UI feel alive and responsive.
*   **Layout:** A sidebar navigation (Dashboard, Resources, Chats, Messages) with a main content area.

## 4. Core Features & Views

### 4.1. Overview Dashboard
The landing page providing a bird's-eye view of the extracted data.
*   **Key Metrics (KPI Cards):** Total Messages, Total Extracted Links, Total Chats, Links Pending Review.
*   **Activity Timeline (Line Chart):** Message volume over time (aggregated by day/month).
*   **Platform Breakdown (Donut Chart):** Distribution of extracted URLs by platform (e.g., Instagram, YouTube, Google Maps).
*   **Top Contributors (Bar Chart):** Who shares the most links.

### 4.2. Resources / Link Review
The core functional page replacing the Excel sheet.
*   **Interactive Data Grid:** Displays the `resources` table with columns: Platform, Canonical URL, Sender, Context, and Status.
*   **Filtering & Sorting:** Filter by platform, status (`To Review`, `Archived`, `Approved`), or specific chat.
*   **Context Expansion:** Clicking a resource expands a pane showing the exact conversational context (the 3 surrounding messages).
*   **Quick Actions:** Buttons to quickly update the `status` of a resource (e.g., marking a link as "Reviewed").

### 4.3. Chats Registry & Insights
*   **Registry:** A list of all imported chats (`chats` table). Shows metadata: first message date, last message date, and total import count.
*   **Chat Insights Dashboard:** A dedicated drill-down page for a specific chat.
    *   **Filters:** Date range picker to isolate specific timeframes.
    *   **Activity Line/Bar Chart:** Granular visualization of message frequency (hourly/daily depending on timeframe).
    *   **Top Participants:** Lists out active members and their respective message counts.
    *   **Top Platforms:** Shows the most popular resource platforms shared in that specific chat.
*   **AI Chat Summary (LangGraph):** A button that dynamically chunks message history for the selected date range and performs a "rolling summary" via LangGraph and an LLM, rendering a comprehensive textual synopsis of the chat events without blowing out context windows.

### 4.4. Raw Message Explorer
*   A searchable, chronological view of the `messages` table.
*   Useful for debugging or searching for specific keywords outside of extracted URLs.

### 4.5. Ask Your Data (Natural Language Query) ✨
*   A dedicated page with a glowing textarea that accepts plain English questions.
*   Questions are sent to `POST /api/query`, which uses an LLM (OpenAI `gpt-4o-mini`) to generate a safe SQL SELECT, executes it, and returns paginated results.
*   Three visual states: **Hero** (empty, shows example chips), **Loading** (shimmer skeleton + thinking dots), **Results** (SQL disclosure block + dynamic table + pagination).
*   URL values in results are automatically rendered as clickable links.
*   The generated SQL is shown in a collapsible disclosure block for full transparency.
*   See [`docs/nl_query_design.md`](./nl_query_design.md) for the full design specification.

## 5. API Architecture

The FastAPI backend exposes the following REST endpoints to serve the frontend:

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/stats` | `GET` | Returns aggregated metrics (counts, charts data) |
| `/api/chats` | `GET` | Returns list of all chats |
| `/api/chats/{id}/insights` | `GET` | Returns aggregated analytics specific to a single chat |
| `/api/chats/{id}/summary` | `POST` | Triggers the LangGraph summarizer for a chat (w/ date range) |
| `/api/resources` | `GET` | Returns paginated/filtered list of resources with joined context |
| `/api/resources/{id}` | `PATCH`| Updates the `status` or metadata of a specific resource |
| `/api/messages` | `GET` | Returns paginated list of raw messages |
| `/api/query` | `POST` | Translates a natural-language question into SQL and returns paginated results |

## 6. System Architecture Update

```mermaid
flowchart TD
    subgraph Data Pipeline (Python)
        A[WhatsApp Export] --> B(Parser)
        B --> C[(SQLite DB: data/resources.db)]
        C --> D(Enrichment)
    end
    
    subgraph Web UI Layer
        E[FastAPI Server] --> |Reads/Writes| C
        F[React Frontend] --> |REST/JSON| E
        
        G((User Browser)) --> |Interacts with| F
    end
```

## 7. Next Steps & Implementation Plan
1.  **Phase 1: Backend Setup:** Initialize FastAPI project in `src/whatsaid/api`, connect it to `core/db.py`, and build read-only endpoints.
2.  **Phase 2: Frontend Scaffolding:** Create Vite + React project, setup global CSS tokens, layout shell, and typography.
3.  **Phase 3: Dashboard & Visualizations:** Integrate Chart.js/Recharts and wire up the `/api/stats` endpoint.
4.  **Phase 4: Resource Review Table:** Build the interactive grid for reviewing links and displaying message context.
5.  **Phase 5: Interactivity:** Implement API calls for updating resource statuses.
