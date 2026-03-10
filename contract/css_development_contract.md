### **MES Dashboard - 前端 CSS 開發契約規範 (v1.0)**

#### **1. 目的**

本契約旨在為 MES Dashboard 專案建立一套清晰、一致、可維護的 CSS 開發標準。透過統一的規範，我們期望能降低開發者的心智負擔、避免樣式衝突、並確保專案長期的程式碼品質。所有前端開發人員在進行樣式相關的開發時，都必須遵守本契約。

---

#### **2. 設計規範 (Design Tokens) 管理**

**原則：`tailwind.config.js` 是唯一真實來源 (Single Source of Truth)。**

*   **契約 2.1**: **禁止**在任何 `.css` 檔案的 `:root` 中手動定義設計規範（如顏色、間距、字體大小等）。
*   **契約 2.2**: 所有新的設計規範**必須**被新增至 `frontend/tailwind.config.js` 檔案的 `theme.extend` 物件中。
*   **契約 2.3**: 在 CSS 檔案中如需使用設計規範，**必須**透過 Tailwind 的 `theme()` 函式來引用。
    *   **範例**：
        ```css
        /* 正確做法 */
        .header-gradient {
          background: linear-gradient(135deg, theme('colors.brand.500') 0%, theme('colors.accent.500') 100%);
        }

        /* 錯誤做法 */
        .header-gradient {
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); /* 硬編碼 */
        }
        .header-gradient {
          background: linear-gradient(135deg, var(--portal-brand-start) 0%, var(--portal-brand-end) 100%); /* 引用非 tailwind.config.js 的變數 */
        }
        ```

---

#### **3. 樣式決策框架**

**原則：優先使用功能類別，僅在必要時進行抽象化。**

*   **契約 3.1 (功能優先原則)**：佈局和樣式開發應**優先**使用 `tailwind.config.js` 中已定義好的 Tailwind 功能類別。
    *   **範例**：使用 `flex items-center rounded-lg` 而非撰寫一個新的 class。

*   **契約 3.2 (抽象化原則)**：當一組「功能類別的組合」在專案中重複出現 **3 次以上**時，應將其抽象化為一個語意化的元件類別。
    *   **契約 3.2.1**: 此類別應使用 `@apply` 來組合 Tailwind 的功能類別。
    *   **契約 3.2.2 (全域元件)**: 如果該元件是**全域複用**的（如按鈕、輸入框、徽章），其類別**必須**定義在 `frontend/src/styles/tailwind.css` 的 `@layer components` 中，並以 `ui-` 作為前綴。
        *   **範例**:
            ```css
            @layer components {
              .ui-button {
                @apply px-4 py-2 bg-brand-500 text-white rounded-md transition-colors hover:bg-brand-600;
              }
            }
            ```
    *   **契約 3.2.3 (複雜樣式)**: 當樣式無法透過 Tailwind 功能類別實現時（例如 `::before` 偽元素、複雜的 `calc()`），才在對應的元件類別中撰寫原生 CSS，但仍需使用 `theme()` 引用設計規範。

*   **契約 3.3 (禁止行內樣式)**：**嚴格禁止**在 Vue 元件的 `<template>` 中直接使用 `style="..."` 來定義靜態樣式。它僅可用於綁定動態計算的樣式。

---

#### **4. 樣式作用域與隔離**

**原則：功能區塊的樣式必須被隔離，禁止汙染全域。**

*   **契約 4.1**: 功能區塊的樣式檔（如 `resource-shared/styles.css`, `wip-shared/styles.css`）**嚴禁**包含對 `html`, `body`, `*` 等全域標籤的樣式定義。
*   **契約 4.2**: 每個主要功能區塊**必須**定義一個唯一的「主題根類別」（Theme Root Class），例如 `.theme-resource`, `.theme-wip`。此類別應被應用於該功能區塊的最外層容器元素上。
*   **契約 4.3**: 特定功能區塊的所有樣式規則，**必須**以其「主題根類別」作為父選擇器，以確保其樣式不會洩漏至區塊外部。
    *   **範例** (在 `resource-shared/styles.css` 中):
        ```css
        /* 正確做法 */
        .theme-resource .summary-card {
          border: 1px solid theme('colors.stroke.panel');
          box-shadow: theme('boxShadow.panel');
        }

        .theme-resource {
           /* 此處可定義僅在此主題下生效的 CSS 變數 */
          --header-height: 56px;
        }

        /* 錯誤做法 */
        .summary-card { /* 缺少 .theme-resource 作用域 */
           border: 1px solid theme('colors.stroke.panel');
        }
        ```

---

#### **5. 基礎樣式與重置 (Base Styles & Resets)**

**原則：`preflight` 已被禁用，所有基礎樣式必須集中管理。**

*   **契約 5.1**: 專案中所有的全域基礎樣式和 CSS 重置（例如 `box-sizing`, `body` 的基礎字體和背景色），**必須**統一在 `frontend/src/styles/tailwind.css` 檔案的 `@layer base` 中定義。
*   **契約 5.2**: 除上述檔案外，任何其他 CSS 檔案**嚴禁**包含自己的基礎樣式重置。

---

#### **6. CSS 清單同步治理 (CSS Inventory Governance)**

**原則：CSS 檔案清單必須可追蹤且與實際程式碼同步。**

*   **契約 6.1**: `contract/css_inventory.md` 為前端 CSS 來源檔清單（`frontend/src/**/*.css`）的治理索引。
*   **契約 6.2**: 若有新增、刪除、重新命名、搬移任何 `frontend/src/**/*.css` 檔案，必須在**同一個變更**同步更新 `contract/css_inventory.md`。
*   **契約 6.3**: 若 CSS 規則大幅搬移（例如從 route-local 移至 shared layer），也必須同步更新清單中的 scope/notes 欄位，避免清單與實際結構失真。
*   **契約 6.4**: `src/mes_dashboard/static/dist/*` 產物檔案不屬於清單治理範圍，不得手動維護於此清單。

---

### **快速參考備忘錄**

| 當您需要... | 您應該... | 操作的檔案 |
| :--- | :--- | :--- |
| 新增一個**顏色**或**間距** | 在 `theme.extend` 中新增 | `tailwind.config.js` |
| 製作一個**一次性**的卡片佈局 | 在 Vue 模板中直接使用 Tailwind **功能類別** | `YourComponent.vue` |
| 建立一個到處都會用的**通用按鈕** | 在 `@layer components` 中建立 `.ui-button` 類別 | `styles/tailwind.css` |
| 建立一個只在**設備管理頁**使用的圖表樣式 | 在 `.theme-resource` 下建立對應類別 | `resource-shared/styles.css` |
| 修改全站的**預設背景色**或**字體** | 修改 `@layer base` 中的 `body` 規則 | `styles/tailwind.css` |
| 新增/刪除/改名一個 CSS 檔案 | 同步更新 CSS 清單並一併提交 | `contract/css_inventory.md` |
