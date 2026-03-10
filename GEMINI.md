# GEMINI.md: MES Dashboard (v2)

This document provides a comprehensive overview of the MES Dashboard project, its architecture, and development practices to be used as instructional context for future interactions. This is the primary source of truth for all development.

## 1. Project Overview

The MES Dashboard is a full-stack web application for Manufacturing Execution System (MES) data reporting and visualization.

*   **Backend:** Python 3.11+ with Flask, Gunicorn, and SQLAlchemy. It uses Redis for caching.
*   **Frontend:** A Vite-based project progressively migrating to Vue 3. It uses Tailwind CSS for styling.
*   **Database:** Oracle Database 19c.
*   **Architecture:** The project features a clear separation of concerns with a `src/mes_dashboard` directory for the backend (containing `routes`, `services`, and `core` modules) and a `frontend` directory for the Vue.js application.

## 2. Core Development Contracts

**This is the most important section.** The project's quality and consistency are maintained by a set of development contracts located in the `/contract` directory. All development, refactoring, or bug-fixing activities **must** strictly adhere to these contracts.

Before making any code changes, review the full contracts.

### **2.1 API Contract (`contract/api_development_contract.md`)**

*   **Core Principle:** All API endpoints **must** use the response helpers from `src/mes_dashboard/core/response.py` (`success_response`, `error_response` series). Manual response creation with `jsonify` is forbidden.
*   **Response Structure:** All responses must conform to the standard success/error envelope defined in the contract.
*   **Error Handling:** All errors must use the predefined error codes (e.g., `VALIDATION_ERROR`, `NOT_FOUND`).
*   **Architecture:** Controllers in the `routes` directory must remain "thin," with all business logic delegated to the `services` directory.

### **2.2 CSS Contract (`contract/css_development_contract.md`)**

*   **Core Principle:** `tailwind.config.js` is the single source of truth for all design tokens (colors, spacing, etc.).
*   **Styling Method:** Follow the "Styling Decision Framework." Use Tailwind utility classes first. Abstract repeated patterns into component classes using `@apply`.
*   **Scoping:** Feature-specific styles (e.g., for "Resource" or "WIP" pages) **must** be scoped under a theme class (e.g., `.theme-resource`) to prevent global conflicts.

## 3. Building and Running

### First-Time Setup

1.  **Run the deployment script:**
    ```bash
    ./scripts/deploy.sh
    ```
2.  **Configure the environment:**
    ```bash
    nano .env
    ```

### Starting the Server

To start the development server (Gunicorn + watchdog):
```bash
./scripts/start_server.sh start
```
The application will be available at `http://localhost:8080`.

### Other Commands

*   **Stop:** `./scripts/start_server.sh stop`
*   **Restart:** `./scripts/start_server.sh restart`
*   **Status:** `./scripts/start_server.sh status`
*   **Logs:** `./scripts/start_server.sh logs follow`

### Frontend Development

*   **Install dependencies:** `npm --prefix frontend install`
*   **Build for production:** `npm --prefix frontend run build`

## 4. Testing

Run the test suite using `pytest`:
```bash
# Run all tests
pytest tests/ -v
```
