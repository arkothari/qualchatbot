const TOKEN_KEY = "qual_admin_token";

export const getAdminToken = () => sessionStorage.getItem(TOKEN_KEY) || "";
export const setAdminToken = (t) => sessionStorage.setItem(TOKEN_KEY, t);

async function request(path, { method = "GET", body, admin = false, form } = {}) {
  const headers = {};
  if (admin) headers["X-Admin-Token"] = getAdminToken();
  let payload;
  if (form) payload = form;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`/api${path}`, { method, headers, body: payload });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {}
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export const api = {
  config: () => request("/config"),
  adminCheck: () => request("/admin/check", { admin: true }),
  listClients: () => request("/clients"),
  getClient: (id) => request(`/clients/${id}`),
  createClient: (name, description) =>
    request("/clients", { method: "POST", body: { name, description }, admin: true }),
  patchClient: (id, patch) =>
    request(`/clients/${id}`, { method: "PATCH", body: patch, admin: true }),
  deleteClient: (id) => request(`/clients/${id}`, { method: "DELETE", admin: true }),
  uploadFile: (id, kind, file) => {
    const form = new FormData();
    form.append("file", file);
    return request(`/clients/${id}/files/${kind}`, { method: "PUT", form, admin: true });
  },
  deleteFile: (id, kind) =>
    request(`/clients/${id}/files/${kind}`, { method: "DELETE", admin: true }),
  schema: (id) => request(`/clients/${id}/schema`),
  chat: (id, messages, model, detail) =>
    request(`/clients/${id}/chat`, { method: "POST", body: { messages, model, detail } }),
};
