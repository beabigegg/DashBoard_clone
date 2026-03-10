# Codex / Agent Code Generation Guide: MES Dashboard

This guide provides instructions for generating code that is compliant with the MES Dashboard project's architecture and conventions.

## Tech Stack

*   **Backend:** Python 3.11+, Flask, SQLAlchemy
*   **Frontend:** Vue 3, Vite, JavaScript
*   **Styling:** Tailwind CSS

---

## Code Generation Guidelines

### **Backend: API Endpoint Generation (Python/Flask)**

**CRITICAL RULE:** All API responses **MUST** be generated using the helpers from `src/mes_dashboard/core/response.py`. Do not generate manual `jsonify` calls.

**GOOD Example (Correct Code):**
```python
from flask import Blueprint
from mes_dashboard.core.response import success_response, validation_error, not_found_error
from mes_dashboard.services import my_service

# All routes are in Blueprints
example_bp = Blueprint('example', __name__, url_prefix='/api/example')

@example_bp.route('/items/<item_id>', methods=['GET'])
def get_item(item_id: int):
    """
    1. Route is "thin".
    2. Calls a service for business logic.
    3. Uses response helpers.
    """
    if not item_id > 0:
        # Use validation_error() for bad input
        return validation_error("Invalid item ID.")

    item = my_service.get_item_by_id(item_id)

    if item is None:
        # Use not_found_error() for missing resources
        return not_found_error("Item not found.")

    # Use success_response() for successful requests
    return success_response(item)

```

**BAD Example (Incorrect Code to Avoid):**
```python
# DO NOT GENERATE CODE LIKE THIS
from flask import jsonify

@example_bp.route('/items/<item_id>', methods=['GET'])
def get_item_bad(item_id: int):
    # Manually creating JSON responses is forbidden
    if not item_id > 0:
        return jsonify({"success": False, "error": "Invalid ID"}), 400

    item = get_item_by_id(item_id) # Business logic in controller is forbidden

    if item is None:
        return jsonify({"success": False, "error": "Not found"}), 404

    return jsonify({"success": True, "data": item})
```

---

### **Frontend: Styling and CSS Class Generation (Vue/Tailwind)**

**CRITICAL RULE:** Follow the styling hierarchy defined in `contract/css_development_contract.md`.

**1. Use Tailwind Utility Classes**
For all standard styling, generate components that use Tailwind's utility classes directly in the template.

**GOOD Example:**
```html
<template>
  <div class="p-4 bg-white rounded-lg shadow-md">
    <h3 class="text-lg font-bold text-gray-800">Card Title</h3>
    <p class="mt-2 text-gray-600">This is a simple card component.</p>
  </div>
</template>
```

**2. Abstracting with `@apply`**
If you need to create a new reusable component style, generate the CSS for the appropriate file using `@apply`.

**GOOD Example (for `styles/tailwind.css`):**
```css
@layer components {
  .ui-card {
    @apply p-4 bg-white rounded-lg shadow-md;
  }
  .ui-card-title {
    @apply text-lg font-bold text-gray-800;
  }
}
```

**3. Scoping Feature-Specific Styles**
If generating styles for a specific feature (e.g., "Resource"), you MUST prefix them with the feature's theme class.

**GOOD Example (for `resource-shared/styles.css`):**
```css
/* All rules are prefixed with .theme-resource */
.theme-resource .resource-summary-widget {
  @apply border border-blue-200 bg-blue-50 p-4;
}
```

**BAD Example (Incorrect Code to Avoid):**
```html
<!-- Do not use style="..." for static styles -->
<div style="padding: 1rem; background-color: white;">...</div>
```
```css
/* Do not add global rules in feature-specific files */
body {
  background-color: #f1f5f9;
}
```

---

### **Canonical Source of Truth**

The master contracts for all development are in the `/contract` directory. Consult them for details.
*   `contract/api_development_contract.md`
*   `contract/css_development_contract.md`
*   `contract/css_inventory.md`
