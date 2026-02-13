function getCsrfToken() {
  return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

function resolveErrorMessage(status, payload) {
  if (payload?.error?.message) {
    return String(payload.error.message);
  }
  if (typeof payload?.error === 'string') {
    return payload.error;
  }
  if (typeof payload?.message === 'string' && payload.message) {
    return payload.message;
  }
  return `匯出失敗 (${status})`;
}

function resolveDownloadFilename(response, fallbackName) {
  const disposition = response.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename=([^;]+)/i);
  if (!match?.[1]) {
    return fallbackName;
  }
  return match[1].replace(/(^['\"]|['\"]$)/g, '').trim() || fallbackName;
}

export async function exportCsv({ exportType, params = {}, fallbackFilename = null }) {
  if (!exportType) {
    throw new Error('缺少匯出類型');
  }

  const headers = {
    'Content-Type': 'application/json',
  };

  const csrfToken = getCsrfToken();
  if (csrfToken) {
    headers['X-CSRF-Token'] = csrfToken;
  }

  const response = await fetch('/api/query-tool/export-csv', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      export_type: exportType,
      params,
    }),
  });

  if (!response.ok) {
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    throw new Error(resolveErrorMessage(response.status, payload));
  }

  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  const link = document.createElement('a');
  const filename = resolveDownloadFilename(
    response,
    fallbackFilename || `${exportType}.csv`,
  );

  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(href);

  return filename;
}
