/**
 * Toast Notification System
 *
 * Usage:
 *   Toast.info('訊息內容');
 *   Toast.success('操作成功');
 *   Toast.warning('請注意');
 *   Toast.error('發生錯誤');
 *   Toast.error('連線失敗', { retry: () => loadData() });
 *
 *   const id = Toast.loading('載入中...');
 *   Toast.update(id, { type: 'success', message: '完成!' });
 *   Toast.dismiss(id);
 */
const Toast = (function() {
    'use strict';

    const MAX_TOASTS = 5;
    const AUTO_DISMISS = {
        info: 3000,
        success: 2000,
        warning: 5000,
        error: null,      // no auto dismiss
        loading: null     // no auto dismiss
    };

    const ICONS = {
        info: 'ℹ',
        success: '✓',
        warning: '⚠',
        error: '✗',
        loading: '⟳'
    };

    let toastId = 0;
    const activeToasts = new Map();

    /**
     * Get or create the toast container
     */
    function getContainer() {
        let container = document.getElementById('mes-toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'mes-toast-container';
            container.className = 'mes-toast-container';
            document.body.appendChild(container);
        }
        return container;
    }

    /**
     * Create a toast element
     */
    function createToastElement(id, type, message, options) {
        const toast = document.createElement('div');
        toast.id = `mes-toast-${id}`;
        toast.className = `mes-toast mes-toast-${type}`;
        toast.setAttribute('role', 'alert');

        // Icon
        const icon = document.createElement('span');
        icon.className = 'mes-toast-icon';
        icon.textContent = ICONS[type];
        toast.appendChild(icon);

        // Message
        const msg = document.createElement('span');
        msg.className = 'mes-toast-message';
        msg.textContent = message;
        toast.appendChild(msg);

        // Retry button (for error type with retry callback)
        if (type === 'error' && options && typeof options.retry === 'function') {
            const retryBtn = document.createElement('button');
            retryBtn.className = 'mes-toast-retry';
            retryBtn.textContent = '重試';
            retryBtn.onclick = function(e) {
                e.stopPropagation();
                dismiss(id);
                options.retry();
            };
            toast.appendChild(retryBtn);
        }

        // Close button
        const closeBtn = document.createElement('button');
        closeBtn.className = 'mes-toast-close';
        closeBtn.innerHTML = '&times;';
        closeBtn.onclick = function(e) {
            e.stopPropagation();
            dismiss(id);
        };
        toast.appendChild(closeBtn);

        return toast;
    }

    /**
     * Enforce max toasts limit - remove oldest if exceeded
     */
    function enforceMaxToasts() {
        while (activeToasts.size >= MAX_TOASTS) {
            const oldestId = activeToasts.keys().next().value;
            dismiss(oldestId);
        }
    }

    /**
     * Show a toast notification
     */
    function show(type, message, options) {
        enforceMaxToasts();

        const id = ++toastId;
        const container = getContainer();
        const toast = createToastElement(id, type, message, options);

        // Insert at the top (newest first)
        container.insertBefore(toast, container.firstChild);

        // Track active toast
        const toastData = { element: toast, type, message, options, timerId: null };
        activeToasts.set(id, toastData);

        // Auto dismiss if applicable
        const dismissTime = AUTO_DISMISS[type];
        if (dismissTime) {
            toastData.timerId = setTimeout(() => dismiss(id), dismissTime);
        }

        return id;
    }

    /**
     * Update an existing toast
     */
    function update(id, updates) {
        const toastData = activeToasts.get(id);
        if (!toastData) {
            return false;
        }

        const { element, timerId } = toastData;

        // Clear existing auto-dismiss timer
        if (timerId) {
            clearTimeout(timerId);
            toastData.timerId = null;
        }

        // Update type if provided
        if (updates.type && updates.type !== toastData.type) {
            element.className = `mes-toast mes-toast-${updates.type}`;
            const icon = element.querySelector('.mes-toast-icon');
            if (icon) {
                icon.textContent = ICONS[updates.type];
            }
            toastData.type = updates.type;

            // Set auto-dismiss for new type
            const dismissTime = AUTO_DISMISS[updates.type];
            if (dismissTime) {
                toastData.timerId = setTimeout(() => dismiss(id), dismissTime);
            }
        }

        // Update message if provided
        if (updates.message !== undefined) {
            const msg = element.querySelector('.mes-toast-message');
            if (msg) {
                msg.textContent = updates.message;
            }
            toastData.message = updates.message;
        }

        return true;
    }

    /**
     * Dismiss a toast
     */
    function dismiss(id) {
        const toastData = activeToasts.get(id);
        if (!toastData) {
            return false;
        }

        const { element, timerId } = toastData;

        // Clear timer
        if (timerId) {
            clearTimeout(timerId);
        }

        // Add exit animation
        element.classList.add('mes-toast-exit');

        // Remove after animation
        setTimeout(() => {
            if (element.parentNode) {
                element.parentNode.removeChild(element);
            }
        }, 300);

        activeToasts.delete(id);
        return true;
    }

    /**
     * Dismiss all toasts
     */
    function dismissAll() {
        for (const id of activeToasts.keys()) {
            dismiss(id);
        }
    }

    // Public API
    return {
        info: function(message, options) {
            return show('info', message, options);
        },
        success: function(message, options) {
            return show('success', message, options);
        },
        warning: function(message, options) {
            return show('warning', message, options);
        },
        error: function(message, options) {
            return show('error', message, options);
        },
        loading: function(message, options) {
            return show('loading', message, options);
        },
        update: update,
        dismiss: dismiss,
        dismissAll: dismissAll
    };
})();
