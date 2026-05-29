const API_ROOT = window.__BREATHE_API_ROOT__ || "/api";

async function request(path, options = {}) {
  const response = await fetch(`${API_ROOT}${path}`, options);
  const isJson = response.headers.get("content-type")?.includes("application/json");
  const payload = isJson ? await response.json() : await response.text();
  if (!response.ok) {
    const message = payload?.detail || payload || "Request failed";
    throw new Error(message);
  }
  return payload;
}

export function getBootstrap(tenant) {
  return request(`/bootstrap/?tenant=${tenant}`);
}

export function getDashboard(tenant) {
  return request(`/dashboard/?tenant=${tenant}`);
}

export function getActivities(tenant, filters) {
  const params = new URLSearchParams({ tenant });
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  return request(`/activities/?${params.toString()}`);
}

export function getAuditEvents(tenant, filters = {}) {
  const params = new URLSearchParams({ tenant });
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  return request(`/audit-events/?${params.toString()}`);
}

export function uploadBatch(tenant, sourceKind, file) {
  const body = new FormData();
  body.append("tenant", tenant);
  body.append("source_kind", sourceKind);
  body.append("file", file);
  return request("/batches/", { method: "POST", body });
}

export function approveActivity(tenant, id, note) {
  return request(`/activities/${id}/approve/?tenant=${tenant}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note })
  });
}

export function rejectActivity(tenant, id, note) {
  return request(`/activities/${id}/reject/?tenant=${tenant}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note })
  });
}

export function reopenActivity(tenant, id, note) {
  return request(`/activities/${id}/reopen/?tenant=${tenant}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note })
  });
}

export function updateActivity(tenant, id, data) {
  return request(`/activities/${id}/?tenant=${tenant}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  });
}
