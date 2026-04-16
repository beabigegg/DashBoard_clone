/**
 * POST-based blob download utility.
 *
 * Sends a POST request with a JSON body, receives a blob response, and
 * triggers a browser file download.  Use this instead of a GET <a href> when
 * filter arrays could make the URL exceed Gunicorn's limit_request_line.
 *
 * @param {string} url      - API endpoint URL
 * @param {object} body     - JSON-serializable request body
 * @param {string} filename - Suggested download filename
 * @throws {Error} On non-2xx responses (message includes status code).
 *                 On HTTP 410: throws with message '410' so callers can
 *                 distinguish dataset-expiry from generic failures.
 */
export async function postExport(url, body, filename) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (response.status === 410) {
    throw Object.assign(new Error('410'), { status: 410 });
  }

  if (!response.ok) {
    throw Object.assign(new Error(`匯出失敗 (HTTP ${response.status})`), {
      status: response.status,
    });
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(objectUrl);
}
