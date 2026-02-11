function normalizeTargetRoute(targetRoute) {
  const route = String(targetRoute || '').trim();
  if (!route) {
    return '/';
  }
  return route.startsWith('/') ? route : `/${route}`;
}

function appendQueryValue(params, key, value) {
  if (value === null || value === undefined) {
    return;
  }
  const text = String(value).trim();
  if (!text) {
    return;
  }
  params.append(key, text);
}

export function buildLaunchHref(targetRoute, query = {}) {
  const normalized = normalizeTargetRoute(targetRoute);
  const [path, rawQuery = ''] = normalized.split('?');
  const params = new URLSearchParams(rawQuery);

  Object.entries(query || {}).forEach(([key, value]) => {
    params.delete(key);
    if (Array.isArray(value)) {
      value.forEach((item) => appendQueryValue(params, key, item));
      return;
    }
    appendQueryValue(params, key, value);
  });

  const queryString = params.toString();
  return queryString ? `${path}?${queryString}` : path;
}
