/* Email Assistant Studio — client */

const state = {
  categories: {},
  importanceLevels: {},
  domainPage: 1,
  contactPage: 1,
  limit: 50,
  selectedDomains: new Set(),
  selectedContacts: new Set(),
  jobPoll: null,
  previewDomain: null,
  previewEmails: [],
  previewDomainCategory: "",
};

const $ = (sel) => document.querySelector(sel);

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...opts.headers },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

function toast(msg, isError = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast show" + (isError ? " error" : "");
  setTimeout(() => el.classList.remove("show"), 3500);
}

function categoryOptions(selected = "") {
  return Object.entries(state.categories)
    .map(([k, v]) => `<option value="${k}" ${k === selected ? "selected" : ""}>${v}</option>`)
    .join("");
}

function fillCategorySelects() {
  const opts = '<option value="">All categories</option>' + categoryOptions();
  $("#domain-category-filter").innerHTML = opts;
  $("#contact-category-filter").innerHTML = opts;
  $("#domain-bulk-category").innerHTML = categoryOptions();
}

function fillImportanceSelects() {
  const opts = importanceOptions();
  const bulk = $("#contact-bulk-importance");
  if (bulk) bulk.innerHTML = opts;
}

function importanceOptions(selected = "medium") {
  const imp = selected && state.importanceLevels[selected] ? selected : "medium";
  return Object.entries(state.importanceLevels)
    .map(([k, v]) => `<option value="${k}" ${k === imp ? "selected" : ""}>${v}</option>`)
    .join("");
}

function normalizeImportance(value) {
  if (value && state.importanceLevels[value]) return value;
  return "medium";
}

async function refreshContactDomainPick() {
  const hideExcluded = $("#contact-hide-excluded").checked;
  const data = await api(
    `/api/domains?hide_excluded=${hideExcluded}&limit=500&sort=message_count&desc=true`
  );
  const sel = $("#contact-domain-filter");
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML =
    '<option value="">All domains</option>' +
    data.items
      .map((d) => `<option value="${d.domain}">${escapeHtml(d.domain)} (${d.message_count})</option>`)
      .join("");
  if (current && [...sel.options].some((o) => o.value === current)) {
    sel.value = current;
  }
}

// --- Navigation ---
document.querySelectorAll("nav button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $(`#panel-${btn.dataset.panel}`).classList.add("active");
    if (btn.dataset.panel === "domains") loadDomains();
    if (btn.dataset.panel === "contacts") {
      refreshContactDomainPick().then(() => loadContacts());
      return;
    }
    if (btn.dataset.panel === "actions") loadJobs();
    if (btn.dataset.panel === "settings") loadTeamSettings();
  });
});

// --- Dashboard ---
async function loadStatus() {
  const s = await api("/api/status");
  $("#team-name").textContent = s.team_name ? `· ${s.team_name}` : "";
  const badges = [];
  badges.push(`<span class="badge ${s.graph_configured ? "ok" : "warn"}">Graph ${s.graph_configured ? "configured" : "not configured"}</span>`);
  badges.push(`<span class="badge ${s.authenticated ? "ok" : "warn"}">${s.authenticated ? "Authenticated" : "Not authenticated"}</span>`);
  $("#status-badges").innerHTML = badges.join(" ");

  $("#dashboard-cards").innerHTML = `
    <div class="card"><div class="label">Domains</div><div class="value">${s.domain_count}</div></div>
    <div class="card"><div class="label">Contacts</div><div class="value">${s.contact_count}</div></div>
    <div class="card"><div class="label">Last scrape</div><div class="value" style="font-size:0.9rem;">${s.scraped_at ? s.scraped_at.slice(0, 16).replace("T", " ") : "—"}</div></div>
    <div class="card"><div class="label">Vault</div><div class="value" style="font-size:0.75rem;word-break:break-all;">${s.vault_path.split("/").pop()}</div></div>
  `;
}

// --- Domains ---
async function loadDomains() {
  const search = $("#domain-search").value;
  const category = $("#domain-category-filter").value;
  const hideExcluded = $("#domain-hide-excluded").checked;
  const data = await api(
    `/api/domains?search=${encodeURIComponent(search)}&category=${encodeURIComponent(category)}&hide_excluded=${hideExcluded}&page=${state.domainPage}&limit=${state.limit}`
  );
  $("#domain-count").textContent = `${data.total} domains`;
  const tbody = $("#domains-tbody");
  tbody.innerHTML = data.items
    .map(
      (d) => `
    <tr data-domain="${d.domain}" class="${state.previewDomain === d.domain ? "active-row" : ""}">
      <td><input type="checkbox" class="domain-cb" value="${d.domain}" ${state.selectedDomains.has(d.domain) ? "checked" : ""} /></td>
      <td><strong>${d.domain}</strong></td>
      <td>${d.message_count}</td>
      <td><select class="cat-select" data-domain="${d.domain}">${categoryOptions(d.category)}</select></td>
      <td style="font-size:0.8rem;color:var(--success)">${d.config_client_abbrev || "—"}</td>
      <td><input type="text" class="company-input" data-domain="${d.domain}" value="${d.company || ""}" /></td>
      <td><button class="secondary preview-btn" data-domain="${d.domain}">Preview</button></td>
    </tr>`
    )
    .join("");

  tbody.querySelectorAll(".cat-select").forEach((sel) => {
    sel.addEventListener("change", () => patchDomain(sel.dataset.domain, { category: sel.value }));
  });
  tbody.querySelectorAll(".company-input").forEach((inp) => {
    inp.addEventListener("blur", () => patchDomain(inp.dataset.domain, { company: inp.value || null }));
  });
  tbody.querySelectorAll(".domain-cb").forEach((cb) => {
    cb.addEventListener("change", () => {
      if (cb.checked) state.selectedDomains.add(cb.value);
      else state.selectedDomains.delete(cb.value);
    });
  });
  tbody.querySelectorAll(".preview-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      openPreviewPanel(btn.dataset.domain);
    });
  });

  renderPagination("domains", data.total, state.domainPage, (p) => {
    state.domainPage = p;
    loadDomains();
  });
}

async function loadDomainContacts(domain) {
  const container = $("#domain-contacts-list");
  if (!domain) {
    container.innerHTML = "";
    return;
  }
  try {
    const data = await api(`/api/domains/${encodeURIComponent(domain)}/contacts`);
    state.previewDomainCategory = data.domain_category || "";
    if (!data.contacts.length) {
      container.innerHTML =
        '<p class="filter-hint">No contacts scraped for this domain yet. Run Scrape inbox.</p>';
      return;
    }
    container.innerHTML = `
      <table class="domain-contacts-table">
        <thead>
          <tr>
            <th>Contact</th>
            <th>Msgs</th>
            <th>Importance</th>
          </tr>
        </thead>
        <tbody>
          ${data.contacts
            .map(
              (c) => `
            <tr>
              <td>
                <div>${escapeHtml(c.name || "—")}</div>
                <div class="contact-email">${escapeHtml(c.email)}</div>
              </td>
              <td>${c.message_count}</td>
              <td>
                <select class="contact-importance" data-email="${escapeHtml(c.email)}">
                  ${importanceOptions(normalizeImportance(c.importance))}
                </select>
              </td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>`;

    container.querySelectorAll(".contact-importance").forEach((sel) => {
      sel.addEventListener("change", () => patchContactImportance(sel.dataset.email, sel.value));
    });
  } catch (e) {
    container.innerHTML = `<p class="filter-hint">${escapeHtml(e.message)}</p>`;
  }
}

async function patchContactImportance(email, importance) {
  try {
    await api(`/api/contacts/${encodeURIComponent(email)}/importance`, {
      method: "PATCH",
      body: JSON.stringify({ importance }),
    });
    toast(`Updated ${email.split("@")[0]}`);
    if (state.previewDomain) await loadDomainContacts(state.previewDomain);
    if ($("#panel-contacts").classList.contains("active")) await loadContacts();
  } catch (e) {
    toast(e.message, true);
    if (state.previewDomain) await loadDomainContacts(state.previewDomain);
    if ($("#panel-contacts").classList.contains("active")) await loadContacts();
  }
}

async function openPreviewPanel(domain) {
  state.previewDomain = domain;
  $("#domains-layout").classList.add("panel-open");
  $("#preview-panel").classList.add("open");
  $("#preview-domain-title").textContent = domain;
  $("#email-detail").style.display = "none";
  $("#suggest-list").innerHTML = "";
  loadDomains();
  await loadDomainContacts(domain);
  await loadDomainPreviews(domain, true);
  await loadClientPicker("");
  await loadClientSuggestions(domain);
}

function closePreviewPanel() {
  state.previewDomain = null;
  state.previewDomainCategory = "";
  $("#domains-layout").classList.remove("panel-open");
  $("#preview-panel").classList.remove("open");
  $("#domain-contacts-list").innerHTML = "";
  loadDomains();
}

async function loadDomainPreviews(domain, live = false) {
  const data = await api(`/api/domains/${encodeURIComponent(domain)}/previews?live=${live}`);
  state.previewEmails = data.previews || [];
  const mapped = data.domain_row?.config_client_abbrev;
  $("#preview-client-mapped").innerHTML = mapped
    ? `<div class="client-mapped">Mapped → <strong>${mapped}</strong> (${data.domain_row.config_client_name || ""})</div>`
    : `<div style="color:var(--muted);font-size:0.85rem;">Not mapped to config.json yet</div>`;

  const container = $("#preview-emails");
  if (!state.previewEmails.length) {
    container.innerHTML = `<p style="color:var(--muted);font-size:0.85rem;">No previews. Click Refresh emails.</p>`;
    return;
  }
  container.innerHTML = state.previewEmails
    .map(
      (e, i) => `
    <div class="email-card" data-idx="${i}" data-msg="${e.message_id || ""}">
      <div class="subject">${escapeHtml(e.subject || "(no subject)")}</div>
      <div class="meta">${escapeHtml(e.sender_name || e.sender_email || "")} · ${(e.received_at || "").slice(0, 16)}</div>
      <div class="body">${escapeHtml(e.body_preview || "(no preview — click for full text)")}</div>
    </div>`
    )
    .join("");

  container.querySelectorAll(".email-card").forEach((card) => {
    card.addEventListener("click", () => showEmailDetail(card.dataset.msg, card.dataset.idx));
  });
}

async function showEmailDetail(messageId, idx) {
  document.querySelectorAll(".email-card").forEach((c) => c.classList.remove("active"));
  const card = document.querySelector(`.email-card[data-idx="${idx}"]`);
  if (card) card.classList.add("active");

  const detail = $("#email-detail");
  detail.style.display = "block";

  if (messageId) {
    try {
      const full = await api(`/api/messages/${encodeURIComponent(messageId)}/preview`);
      detail.innerHTML = `<strong>${escapeHtml(full.subject)}</strong>\n\nFrom: ${escapeHtml(full.sender_email)}\n\n${escapeHtml(full.body_text || full.body_preview)}`;
    } catch {
      const e = state.previewEmails[idx];
      detail.textContent = `${e.subject}\n\n${e.body_preview || ""}`;
    }
  } else {
    const e = state.previewEmails[idx];
    detail.textContent = `${e.subject}\n\n${e.body_preview || "(Re-scrape inbox to capture body previews)"}`;
  }
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function loadClientPicker(search) {
  const clients = await api(`/api/config/clients?search=${encodeURIComponent(search)}&limit=100`);
  const sel = $("#client-picker");
  sel.innerHTML =
    '<option value="">— map to config.json client —</option>' +
    clients
      .map(
        (c) =>
          `<option value="${c.client_abbrev}">${c.client_abbrev} — ${c.client_name.slice(0, 60)}</option>`
      )
      .join("");
}

async function loadClientSuggestions(domain) {
  const data = await api(`/api/domains/${encodeURIComponent(domain)}/suggest-client`);
  const ul = $("#suggest-list");
  if (!data.suggestions?.length) {
    ul.innerHTML = `<li style="cursor:default;color:var(--muted)">No auto-suggestions — search manually</li>`;
    return;
  }
  ul.innerHTML = data.suggestions
    .map(
      (s) =>
        `<li data-abbrev="${s.client_abbrev}"><strong>${s.client_abbrev}</strong> — ${escapeHtml(s.client_name.slice(0, 50))}<br><span style="color:var(--muted)">${escapeHtml(s.reason)}</span></li>`
    )
    .join("");
  ul.querySelectorAll("li[data-abbrev]").forEach((li) => {
    li.addEventListener("click", () => {
      $("#client-picker").value = li.dataset.abbrev;
    });
  });
}

$("#preview-close").addEventListener("click", closePreviewPanel);
$("#btn-suggest-client").addEventListener("click", () => {
  if (state.previewDomain) loadClientSuggestions(state.previewDomain);
});
$("#btn-refresh-previews").addEventListener("click", async () => {
  if (!state.previewDomain) return;
  try {
    const { job_id } = await api(`/api/domains/${encodeURIComponent(state.previewDomain)}/refresh-previews`, {
      method: "POST",
    });
    toast(`Refreshing previews…`);
    pollJob(job_id, () => loadDomainPreviews(state.previewDomain, false));
  } catch (e) {
    toast(e.message, true);
  }
});
$("#client-search").addEventListener(
  "input",
  debounce((e) => loadClientPicker(e.target.value), 300)
);
$("#btn-map-client").addEventListener("click", async () => {
  const abbrev = $("#client-picker").value;
  if (!abbrev || !state.previewDomain) {
    toast("Select a client", true);
    return;
  }
  try {
    await api(`/api/domains/${encodeURIComponent(state.previewDomain)}/map-client`, {
      method: "POST",
      body: JSON.stringify({ client_abbrev: abbrev }),
    });
    toast(`Mapped ${state.previewDomain} → ${abbrev}`);
    loadDomainPreviews(state.previewDomain, false);
    loadDomains();
  } catch (e) {
    toast(e.message, true);
  }
});

async function patchDomain(domain, patch) {
  try {
    await api(`/api/domains/${encodeURIComponent(domain)}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
    toast(`Updated ${domain}`);
  } catch (e) {
    toast(e.message, true);
  }
}

$("#domain-search").addEventListener(
  "input",
  debounce(() => {
    state.domainPage = 1;
    loadDomains();
  }, 300)
);
$("#domain-category-filter").addEventListener("change", () => {
  state.domainPage = 1;
  loadDomains();
});
$("#domain-hide-excluded").addEventListener("change", () => {
  state.domainPage = 1;
  loadDomains();
});

$("#domain-select-all").addEventListener("change", (e) => {
  document.querySelectorAll(".domain-cb").forEach((cb) => {
    cb.checked = e.target.checked;
    if (e.target.checked) state.selectedDomains.add(cb.value);
    else state.selectedDomains.delete(cb.value);
  });
});

$("#domain-bulk-apply").addEventListener("click", async () => {
  const cat = $("#domain-bulk-category").value;
  if (!cat || state.selectedDomains.size === 0) {
    toast("Select domains and a category", true);
    return;
  }
  try {
    const r = await api("/api/domains/bulk", {
      method: "POST",
      body: JSON.stringify({ domains: [...state.selectedDomains], category: cat }),
    });
    toast(`Updated ${r.updated} domains`);
    state.selectedDomains.clear();
    loadDomains();
  } catch (e) {
    toast(e.message, true);
  }
});

// --- Contacts ---
async function loadContacts() {
  const search = $("#contact-search").value;
  const domain = $("#contact-domain-filter").value;
  const category = $("#contact-category-filter").value;
  const importance = $("#contact-importance-filter").value;
  const hideExcluded = $("#contact-hide-excluded").checked;
  const data = await api(
    `/api/contacts?search=${encodeURIComponent(search)}&domain=${encodeURIComponent(domain)}&category=${encodeURIComponent(category)}&importance=${encodeURIComponent(importance)}&hide_excluded=${hideExcluded}&page=${state.contactPage}&limit=${state.limit}`
  );
  const domainLabel = domain ? domain : "all domains";
  $("#contact-count").textContent = `${data.total} contacts · ${domainLabel}`;
  $("#contact-domain-col").style.display = domain ? "none" : "";
  $("#contacts-tbody").innerHTML = data.items
    .map(
      (c) => `
    <tr>
      <td><input type="checkbox" class="contact-cb" value="${escapeHtml(c.email)}" ${state.selectedContacts.has(c.email) ? "checked" : ""} /></td>
      <td>${c.rank}</td>
      <td>${escapeHtml(c.name || "—")}</td>
      <td style="font-size:0.8rem">${escapeHtml(c.email)}</td>
      <td class="contact-domain-cell" style="font-size:0.8rem;${domain ? "display:none" : ""}">${escapeHtml(c.domain)}</td>
      <td>${c.message_count}</td>
      <td>
        <select class="contact-importance" data-email="${escapeHtml(c.email)}">
          ${importanceOptions(normalizeImportance(c.importance))}
        </select>
      </td>
    </tr>`
    )
    .join("");

  document.querySelectorAll(".contact-cb").forEach((cb) => {
    cb.addEventListener("change", () => {
      if (cb.checked) state.selectedContacts.add(cb.value);
      else state.selectedContacts.delete(cb.value);
    });
  });
  document.querySelectorAll(".contact-importance").forEach((sel) => {
    sel.addEventListener("change", () => patchContactImportance(sel.dataset.email, sel.value));
  });

  renderPagination("contacts", data.total, state.contactPage, (p) => {
    state.contactPage = p;
    loadContacts();
  });
}

$("#contact-search").addEventListener(
  "input",
  debounce(() => {
    state.contactPage = 1;
    loadContacts();
  }, 300)
);
$("#contact-category-filter").addEventListener("change", () => {
  state.contactPage = 1;
  loadContacts();
});
$("#contact-domain-filter").addEventListener("change", () => {
  state.contactPage = 1;
  loadContacts();
});
$("#contact-hide-excluded").addEventListener("change", () => {
  state.contactPage = 1;
  refreshContactDomainPick().then(() => loadContacts());
});
$("#contact-importance-filter").addEventListener("change", () => {
  state.contactPage = 1;
  loadContacts();
});

$("#contact-select-all").addEventListener("change", (e) => {
  document.querySelectorAll(".contact-cb").forEach((cb) => {
    cb.checked = e.target.checked;
    if (e.target.checked) state.selectedContacts.add(cb.value);
    else state.selectedContacts.delete(cb.value);
  });
});

$("#contact-bulk-apply").addEventListener("click", async () => {
  const imp = $("#contact-bulk-importance").value;
  if (!imp || state.selectedContacts.size === 0) {
    toast("Select contacts and an importance level", true);
    return;
  }
  try {
    const r = await api("/api/contacts/bulk", {
      method: "POST",
      body: JSON.stringify({ emails: [...state.selectedContacts], importance: imp }),
    });
    toast(`Updated ${r.updated} contacts`);
    state.selectedContacts.clear();
    loadContacts();
  } catch (e) {
    toast(e.message, true);
  }
});

// --- Actions ---
async function runAction(endpoint, body) {
  try {
    const { job_id } = await api(endpoint, { method: "POST", body: JSON.stringify(body || {}) });
    toast(`Job started: ${job_id}`);
    pollJob(job_id);
    loadJobs();
  } catch (e) {
    toast(e.message, true);
  }
}

$("#btn-scrape").addEventListener("click", () =>
  runAction("/api/actions/scrape", { max_pages: parseInt($("#scrape-pages").value, 10) || 100 })
);
$("#btn-categorize").addEventListener("click", () => runAction("/api/actions/categorize"));
$("#btn-apply").addEventListener("click", () => runAction("/api/actions/apply"));

function pollJob(jobId, onComplete) {
  if (state.jobPoll) clearInterval(state.jobPoll);
  state.jobPoll = setInterval(async () => {
    const job = await api(`/api/jobs/${jobId}`);
    loadJobs();
    if (job.status === "completed" || job.status === "failed") {
      clearInterval(state.jobPoll);
      toast(job.status === "completed" ? job.message : job.error, job.status === "failed");
      loadStatus();
      if (onComplete && job.status === "completed") onComplete();
    }
  }, 1500);
}

async function loadJobs() {
  const jobs = await api("/api/jobs");
  $("#job-log").innerHTML = jobs.length
    ? jobs
        .map(
          (j) =>
            `<div class="job-item"><strong>${j.name}</strong> · ${j.status} · ${j.message || j.error || ""} <span style="color:var(--muted)">${(j.finished_at || j.created_at || "").slice(0, 19)}</span></div>`
        )
        .join("")
    : "<div style='color:var(--muted)'>No jobs yet</div>";
}

// --- Settings ---
function objToYaml(obj) {
  return Object.entries(obj)
    .map(([k, v]) => `${k}: ${v}`)
    .join("\n");
}

function yamlToObj(text) {
  const out = {};
  text.split("\n").forEach((line) => {
    const m = line.match(/^([^:]+):\s*(.+)$/);
    if (m) out[m[1].trim()] = m[2].trim().replace(/^["']|["']$/g, "");
  });
  return out;
}

async function loadTeamSettings() {
  const t = await api("/api/team");
  $("#set-team-name").value = t.team_name || "";
  $("#set-organization").value = t.organization || "";
  $("#set-tenant-id").value = t.tenant_id || "";
  $("#set-vault-path").value = t.vault_path || "vault";
  $("#set-max-pages").value = t.scrape_defaults?.max_pages || 100;
  $("#set-max-agents").value = t.agent_defaults?.max_agents || 25;
  $("#set-domain-hints").value = objToYaml(t.domain_hints || {});
  $("#set-categories").value = objToYaml(t.categories || {});
}

$("#btn-save-team").addEventListener("click", async () => {
  try {
    const body = {
      team_name: $("#set-team-name").value,
      organization: $("#set-organization").value,
      tenant_id: $("#set-tenant-id").value,
      vault_path: $("#set-vault-path").value,
      data_dir: "data",
      scrape_defaults: {
        max_pages: parseInt($("#set-max-pages").value, 10) || 100,
        page_size: 100,
      },
      agent_defaults: {
        max_agents: parseInt($("#set-max-agents").value, 10) || 25,
        min_messages_for_company: 3,
      },
      domain_hints: yamlToObj($("#set-domain-hints").value),
      categories: yamlToObj($("#set-categories").value),
    };
    await api("/api/team", { method: "PUT", body: JSON.stringify(body) });
    state.categories = body.categories;
    fillCategorySelects();
    fillImportanceSelects();
    toast("Team config saved");
    loadStatus();
  } catch (e) {
    toast(e.message, true);
  }
});

// --- Helpers ---
function renderPagination(prefix, total, page, onPage) {
  const pages = Math.ceil(total / state.limit) || 1;
  const el = $(`#${prefix}-pagination`);
  el.innerHTML = `
    <button class="secondary" ${page <= 1 ? "disabled" : ""} data-p="${page - 1}">Prev</button>
    <span>Page ${page} of ${pages}</span>
    <button class="secondary" ${page >= pages ? "disabled" : ""} data-p="${page + 1}">Next</button>
  `;
  el.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!btn.disabled) onPage(parseInt(btn.dataset.p, 10));
    });
  });
}

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

// --- Init ---
async function init() {
  const [categories, importanceLevels] = await Promise.all([
    api("/api/categories"),
    api("/api/contact-importance-levels"),
  ]);
  state.categories = categories;
  state.importanceLevels = importanceLevels;
  fillCategorySelects();
  fillImportanceSelects();
  await loadStatus();
}

init();
