# Claude Development Guide: MES Dashboard

This document contains the essential rules and guidelines you must follow when developing for the MES Dashboard project. Your primary goal is to ensure all code modifications adhere strictly to the established contracts.

## Project Overview

*   **Tech Stack:** The backend is a Python/Flask application. The frontend is a Vue 3/Vite application styled with Tailwind CSS.
*   **Architecture:** The project enforces a strong separation of concerns.
    *   Backend logic is separated into `routes` (HTTP layer) and `services` (business logic layer).
    *   Frontend components are modular, with global components in `shared-ui` and feature-specific components in directories like `resource-shared`.

## Core Development Rules

You are an expert developer. Before making any changes, you must consult the canonical contracts located in the `/contract` directory. The following is a summary of the most critical rules.

---

### **Rule #1: API Development MUST Follow the API Contract**

Reference the full contract: `contract/api_development_contract.md`

*   **1.1 - Use Response Helpers:** You **MUST NOT** use `jsonify` manually. All API responses must be generated using the helpers from `src/mes_dashboard/core/response.py`.
    *   For success: `return success_response(data, ...)`
    *   For errors: `return validation_error(message, ...)` or `return not_found_error(...)`

*   **1.2 - Standard Error Codes:** All thrown errors must use a predefined error code string from `core/response.py` (e.g., `VALIDATION_ERROR`, `INTERNAL_ERROR`).

*   **1.3 - Keep Routes Thin:** Do not place business logic in the `routes/*.py` files. Place it in the corresponding `services/*.py` file and call the service from the route.

---

### **Rule #2: CSS Development MUST Follow the CSS Contract**

Reference the full contract: `contract/css_development_contract.md`
Reference the governed CSS source inventory: `contract/css_inventory.md`

*   **2.1 - Single Source of Truth for Design:** All design tokens (colors, spacing, fonts) are defined in `tailwind.config.js`. You **MUST NOT** hard-code values (like `#FFFFFF`) in components. Use Tailwind's utility classes (e.g., `bg-white`, `p-4`).

*   **2.2 - Styling Hierarchy:** Follow this decision process:
    1.  Always attempt to use Tailwind utility classes first.
    2.  If utilities are repeated, create a component class with `@apply` in the appropriate CSS file (`styles/tailwind.css` for global, or a feature-specific file like `resource-shared/styles.css`).
    3.  Only write custom CSS for properties Tailwind cannot handle.

*   **2.3 - Isolate Feature Styles:** When adding styles for a specific feature (e.g., "Resource" pages), you **MUST** scope the styles under that feature's theme class (e.g., `.theme-resource .my-new-class { ... }`). You **MUST NOT** add global styles (like for `body` or `*`) in a feature-specific file.
*   **2.4 - Keep CSS Inventory in Sync:** If a CSS source file is added/removed/renamed/moved under `frontend/src/**/*.css`, you **MUST** update `contract/css_inventory.md` in the same change.

---

## Project Commands

*   **Start Server:** `./scripts/start_server.sh start`
*   **Stop Server:** `./scripts/start_server.sh stop`
*   **Run All Tests:** `pytest tests/ -v`
