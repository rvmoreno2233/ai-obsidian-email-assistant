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
  previewContact: null,
  contactPreviewEmails: [],
  contactKeyPhrases: [],
};

const $ = (sel) => document.querySelector(sel);

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...opts.headers },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err = new Error(formatApiError(res.status, body));
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return res.json();
}

function formatApiError(status, body) {
  const detail = body?.detail;
  if (detail && typeof detail === "object") {
    if (Array.isArray(detail.issues) && detail.issues.length) {
      return detail.issues.map((i) => `${i.message} ${i.fix}`).join(" · ");
    }
    if (detail.message) return detail.message;
  }
  if (typeof detail === "string") return detail;
  if (status === 405) {
    return "Method not allowed — restart Studio so the latest API is loaded (email-assistant ui).";
  }
  if (status === 503) {
    return "Live email refresh unavailable — check .env and authentication (see setup steps below).";
  }
  return detail || body?.message || `Request failed (${status})`;
}

function renderContactSetupHint(issues) {
  const el = $("#contact-preview-setup");
  if (!el) return;
  if (!issues?.length) {
    el.style.display = "none";
    el.innerHTML = "";
    return;
  }
  el.style.display = "block";
  el.innerHTML = `
    <strong>Setup needed to refresh emails from Outlook</strong>
    <ol>
      ${issues
        .map(
          (i) =>
            `<li><span>${escapeHtml(i.message)}</span><code class="setup-fix">${escapeHtml(i.fix)}</code></li>`
        )
        .join("")}
    </ol>`;
}

async function refreshContactSetupHint() {
  try {
    const status = await api("/api/status");
    renderContactSetupHint(status.email_refresh_issues || []);
    const btn = $("#btn-contact-refresh-previews");
    if (btn) btn.disabled = !status.email_refresh_ready;
  } catch {
    renderContactSetupHint([]);
  }
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
    if (btn.dataset.panel === "knowledge") loadKnowledge();
    if (btn.dataset.panel === "actions") loadJobs();
    if (btn.dataset.panel === "email-settings") loadEmailSettings();
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
  if (s.email_refresh_ready === false) {
    badges.push(`<span class="badge warn" title="Live email refresh needs Graph setup">Refresh: setup needed</span>`);
  }
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
    if (state.previewContact === email) await loadContactPreviews(email, false);
    if ($("#panel-contacts").classList.contains("active")) await loadContacts();
  } catch (e) {
    toast(e.message, true);
    if (state.previewDomain) await loadDomainContacts(state.previewDomain);
    if (state.previewContact === email) await loadContactPreviews(email, false);
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
    card.addEventListener("click", () =>
      showEmailDetail(card.dataset.msg, card.dataset.idx, {
        emails: state.previewEmails,
        detailEl: $("#email-detail"),
        cardSelector: "#preview-emails .email-card",
      })
    );
  });
}

async function showEmailDetail(messageId, idx, options = {}) {
  const {
    emails = state.previewEmails,
    detailEl = $("#email-detail"),
    cardSelector = ".email-card",
  } = options;

  document.querySelectorAll(cardSelector).forEach((c) => c.classList.remove("active"));
  const card = document.querySelector(`${cardSelector}[data-idx="${idx}"]`);
  if (card) card.classList.add("active");

  detailEl.style.display = "block";

  if (messageId) {
    try {
      const full = await api(`/api/messages/${encodeURIComponent(messageId)}/preview`);
      detailEl.innerHTML = `<strong>${escapeHtml(full.subject)}</strong>\n\nFrom: ${escapeHtml(full.sender_email)}\n\n${escapeHtml(full.body_text || full.body_preview)}`;
    } catch {
      const e = emails[idx];
      detailEl.textContent = `${e.subject}\n\n${e.body_preview || ""}`;
    }
  } else {
    const e = emails[idx];
    detailEl.textContent = `${e.subject}\n\n${e.body_preview || "(Re-scrape inbox to capture body previews)"}`;
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
    <tr data-email="${escapeHtml(c.email)}" class="${state.previewContact === c.email ? "active-row" : ""}">
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
      <td><button class="secondary contact-preview-btn" data-email="${escapeHtml(c.email)}">Preview</button></td>
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
  document.querySelectorAll(".contact-preview-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      openContactPreviewPanel(btn.dataset.email);
    });
  });

  renderPagination("contacts", data.total, state.contactPage, (p) => {
    state.contactPage = p;
    loadContacts();
  });
}

function parseKeyPhrases(text) {
  return [...new Set(text.split("\n").map((line) => line.trim()).filter(Boolean))];
}

function renderKeyPhraseChips(phrases) {
  const el = $("#contact-key-phrase-chips");
  if (!el) return;
  if (!phrases.length) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = phrases
    .map(
      (phrase, i) =>
        `<span class="key-phrase-chip" data-idx="${i}">${escapeHtml(phrase)} <button type="button" class="chip-remove" data-idx="${i}" title="Remove">×</button></span>`
    )
    .join("");
  el.querySelectorAll(".chip-remove").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const idx = parseInt(btn.dataset.idx, 10);
      state.contactKeyPhrases.splice(idx, 1);
      syncKeyPhrasesUi();
    });
  });
}

function syncKeyPhrasesUi() {
  $("#contact-key-phrases-input").value = state.contactKeyPhrases.join("\n");
  renderKeyPhraseChips(state.contactKeyPhrases);
}

async function openContactPreviewPanel(email) {
  state.previewContact = email;
  $("#contacts-layout").classList.add("panel-open");
  $("#contact-preview-panel").classList.add("open");
  $("#contact-email-detail").style.display = "none";
  loadContacts();
  await refreshContactSetupHint();
  try {
    await loadContactPreviews(email, true);
  } catch (e) {
    if (e.body?.detail?.issues) {
      renderContactSetupHint(e.body.detail.issues);
    }
    $("#contact-preview-emails").innerHTML =
      `<p class="filter-hint">${escapeHtml(e.message)}</p>`;
  }
}

function closeContactPreviewPanel() {
  state.previewContact = null;
  state.contactPreviewEmails = [];
  state.contactKeyPhrases = [];
  $("#contacts-layout").classList.remove("panel-open");
  $("#contact-preview-panel").classList.remove("open");
  loadContacts();
}

async function loadContactPreviews(email, live = false) {
  const data = await api(`/api/contacts/${encodeURIComponent(email)}/previews?live=${live}`);
  if (data.graph_warning?.issues) {
    renderContactSetupHint(data.graph_warning.issues);
  } else if (data.graph_warning?.message) {
    renderContactSetupHint([{ message: data.graph_warning.message, fix: "See steps above." }]);
  }

  const row = data.contact_row || {};
  state.contactPreviewEmails = data.previews || [];
  state.contactKeyPhrases = [...(row.key_phrases || [])];

  $("#contact-preview-title").textContent = row.name ? `${row.name}` : email;
  $("#contact-preview-meta").innerHTML = `
    <div style="font-size:0.85rem;color:var(--muted);word-break:break-all;">${escapeHtml(email)}</div>
    <div style="font-size:0.8rem;color:var(--muted);margin-top:0.35rem;">
      ${escapeHtml(row.domain || "")} · ${escapeHtml(row.category || "unassigned")} ·
      ${row.message_count || 0} msgs · ${escapeHtml(normalizeImportance(row.importance))} importance
    </div>`;
  syncKeyPhrasesUi();

  const container = $("#contact-preview-emails");
  if (!state.contactPreviewEmails.length) {
    container.innerHTML =
      `<p style="color:var(--muted);font-size:0.85rem;">No previews yet. Complete Graph setup above, then click Refresh emails.</p>`;
    return;
  }
  const cacheNote = data.graph_warning
    ? `<p class="filter-hint">Showing cached subjects — live refresh unavailable until setup is complete.</p>`
    : "";
  container.innerHTML =
    cacheNote +
    state.contactPreviewEmails
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
    card.addEventListener("click", () =>
      showEmailDetail(card.dataset.msg, card.dataset.idx, {
        emails: state.contactPreviewEmails,
        detailEl: $("#contact-email-detail"),
        cardSelector: "#contact-preview-emails .email-card",
      })
    );
  });
}

function addSelectedKeyPhrase() {
  const selection = window.getSelection()?.toString().trim();
  if (!selection) {
    toast("Select text in an email first", true);
    return;
  }
  if (!state.contactKeyPhrases.includes(selection)) {
    state.contactKeyPhrases.push(selection);
  }
  syncKeyPhrasesUi();
  toast("Added key phrase");
}

async function saveContactKeyPhrases() {
  if (!state.previewContact) return;
  const fromInput = parseKeyPhrases($("#contact-key-phrases-input").value);
  state.contactKeyPhrases = fromInput;
  try {
    await api(`/api/contacts/${encodeURIComponent(state.previewContact)}`, {
      method: "PATCH",
      body: JSON.stringify({ key_phrases: state.contactKeyPhrases }),
    });
    toast("Key phrases saved");
    syncKeyPhrasesUi();
  } catch (e) {
    toast(e.message, true);
  }
}

function copyContactKeyPhrases() {
  const text = parseKeyPhrases($("#contact-key-phrases-input").value).join("\n");
  if (!text) {
    toast("No key phrases to copy", true);
    return;
  }
  navigator.clipboard.writeText(text).then(
    () => toast("Copied key phrases"),
    () => toast("Copy failed — select and copy manually", true)
  );
}

$("#contact-preview-close")?.addEventListener("click", closeContactPreviewPanel);
$("#btn-contact-refresh-previews")?.addEventListener("click", async () => {
  if (!state.previewContact) return;
  try {
    const { job_id } = await api(
      `/api/contacts/${encodeURIComponent(state.previewContact)}/refresh-previews`,
      { method: "POST" }
    );
    toast("Refreshing contact emails…");
    pollJob(job_id, () => {
      refreshContactSetupHint();
      loadContactPreviews(state.previewContact, false);
    });
  } catch (e) {
    if (e.body?.detail?.issues) {
      renderContactSetupHint(e.body.detail.issues);
    }
    toast(e.message, true);
  }
});
$("#btn-add-key-phrase")?.addEventListener("click", addSelectedKeyPhrase);
$("#btn-save-key-phrases")?.addEventListener("click", saveContactKeyPhrases);
$("#btn-copy-key-phrases")?.addEventListener("click", copyContactKeyPhrases);
$("#contact-key-phrases-input")?.addEventListener(
  "input",
  debounce(() => {
    state.contactKeyPhrases = parseKeyPhrases($("#contact-key-phrases-input").value);
    renderKeyPhraseChips(state.contactKeyPhrases);
  }, 200)
);

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

// --- Email Settings ---

const emailSettingsState = {
  templates: [],
  rules: [],
  approvalPreviewId: null,
};

function parseKeywords(text) {
  return text
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function formatKeywords(list) {
  return (list || []).join(", ");
}

async function loadEmailSettings() {
  await Promise.all([
    loadOllamaHealth(),
    loadTemplates(),
    loadRules(),
    loadPollerSettings(),
    loadApprovalQueue(),
    loadAutoQueue(),
    loadEmailSettingsJobs(),
  ]);
}

function ollamaModelBase(name) {
  return (name || "").split(":")[0];
}

function ollamaModelsMatch(a, b) {
  return !!a && !!b && (a === b || ollamaModelBase(a) === ollamaModelBase(b));
}

function isOllamaModelReady(configured, models, apiFlag) {
  if (apiFlag === true) return true;
  if (!configured || !models.length) return false;
  return models.some((m) => ollamaModelsMatch(configured, m));
}

function findMatchingOllamaModel(configured, models) {
  if (!configured) return null;
  return models.find((m) => ollamaModelsMatch(configured, m)) || null;
}

async function loadOllamaHealth() {
  const badge = $("#ollama-badge");
  const hostEl = $("#ollama-host");
  const configuredEl = $("#ollama-configured-model");
  const modelSelect = $("#ollama-test-model");
  const modelsList = $("#ollama-models-list");
  try {
    const h = await api("/api/ollama/health");
    badge.textContent = h.ok ? "Connected" : "Unavailable";
    badge.className = "badge " + (h.ok ? "ok" : "warn");
    hostEl.textContent = h.host ? `Host: ${h.host}` : "";

    const models = h.models_available || [];
    const configured = h.model || "";
    const matched = findMatchingOllamaModel(configured, models);
    const ready = isOllamaModelReady(configured, models, h.model_ready);
    configuredEl.innerHTML = ready
      ? `<span class="badge ok">${escapeHtml(configured)}</span> — ready${
          matched && matched !== configured ? ` (installed as <code>${escapeHtml(matched)}</code>)` : ""
        }`
      : `<span class="badge warn">${escapeHtml(configured || "(not set)")}</span> — not installed. Pick a model below and update <code>OLLAMA_MODEL</code> in <code>.env</code>.`;

    modelSelect.innerHTML = models.length
      ? models.map((m) => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join("")
      : '<option value="">No models — run ollama pull …</option>';
    if (matched) {
      modelSelect.value = matched;
    } else if (models.length) {
      modelSelect.value = models[0];
    }

    if (!models.length) {
      modelsList.innerHTML = '<p class="es-empty">No models found. Run <code>ollama pull llama3</code> or similar.</p>';
      return;
    }

    modelsList.innerHTML = models
      .map(
        (m) => `
      <div class="model-test-row" data-model="${escapeHtml(m)}">
        <div class="model-test-name">
          <strong>${escapeHtml(m)}</strong>
          ${ollamaModelsMatch(m, configured) ? '<span class="badge ok">configured</span>' : ""}
        </div>
        <div class="model-test-result" id="model-test-${cssId(m)}"></div>
        <button class="secondary btn-model-test" data-model="${escapeHtml(m)}">Test</button>
      </div>`
      )
      .join("");

    modelsList.querySelectorAll(".btn-model-test").forEach((btn) => {
      btn.addEventListener("click", () => runOllamaModelTest(btn.dataset.model, btn));
    });
  } catch (e) {
    badge.textContent = "Error";
    badge.className = "badge warn";
    hostEl.textContent = e.message;
    configuredEl.textContent = "";
    modelsList.innerHTML = "";
  }
}

function cssId(name) {
  return name.replace(/[^a-zA-Z0-9_-]/g, "_");
}

async function runOllamaModelTest(model, btn) {
  const resultEl = $(`#model-test-${cssId(model)}`);
  if (resultEl) resultEl.textContent = "Running…";
  if (btn) btn.disabled = true;
  try {
    const body = await api("/api/ollama/test", {
      method: "POST",
      body: JSON.stringify({
        prompt: $("#ollama-test-prompt").value,
        model,
      }),
    });
    const text = `OK · ${body.latency_ms} ms · ${body.reply}`;
    if (resultEl) {
      resultEl.textContent = text;
      resultEl.className = "model-test-result ok";
    }
    return body;
  } catch (e) {
    if (resultEl) {
      resultEl.textContent = e.message;
      resultEl.className = "model-test-result error";
    }
    throw e;
  } finally {
    if (btn) btn.disabled = false;
  }
}

$("#btn-ollama-test").addEventListener("click", async () => {
  const result = $("#ollama-test-result");
  const model = $("#ollama-test-model").value;
  if (!model) {
    toast("No model selected", true);
    return;
  }
  result.style.display = "block";
  result.textContent = `Testing ${model}…`;
  try {
    const body = await runOllamaModelTest(model);
    result.textContent = `${body.model}\nOK (${body.latency_ms} ms)\n${body.reply}`;
  } catch (e) {
    result.textContent = `Error: ${e.message}`;
  }
});

async function loadTemplates() {
  const data = await api("/api/templates");
  emailSettingsState.templates = data.items || [];
  renderTemplatesList();
  fillRuleTemplateSelect();
}

function renderTemplatesList() {
  const el = $("#templates-list");
  if (!emailSettingsState.templates.length) {
    el.innerHTML = '<p class="es-empty">No templates yet. Create one to attach to rules.</p>';
    return;
  }
  el.innerHTML = emailSettingsState.templates
    .map(
      (t) => `
    <div class="es-card" data-id="${escapeHtml(t.id)}">
      <div class="es-card-header">
        <strong>${escapeHtml(t.name)}</strong>
        <span class="es-meta">${escapeHtml(t.id)}</span>
      </div>
      <div class="es-card-body">${escapeHtml((t.body || "").slice(0, 120))}${(t.body || "").length > 120 ? "…" : ""}</div>
      <div class="es-card-actions">
        <button class="secondary btn-template-edit" data-id="${escapeHtml(t.id)}">Edit</button>
        <button class="secondary btn-template-delete" data-id="${escapeHtml(t.id)}">Delete</button>
      </div>
    </div>`
    )
    .join("");

  el.querySelectorAll(".btn-template-edit").forEach((btn) => {
    btn.addEventListener("click", () => openTemplateEditor(btn.dataset.id));
  });
  el.querySelectorAll(".btn-template-delete").forEach((btn) => {
    btn.addEventListener("click", () => deleteTemplate(btn.dataset.id));
  });
}

function openTemplateEditor(id) {
  const editor = $("#template-editor");
  editor.style.display = "block";
  if (id) {
    const t = emailSettingsState.templates.find((x) => x.id === id);
    if (!t) return;
    $("#template-edit-id").value = t.id;
    $("#template-name").value = t.name || "";
    $("#template-subject-prefix").value = t.subject_prefix || "Re: ";
    $("#template-body").value = t.body || "";
    $("#template-ai-instructions").value = t.ai_instructions || "";
  } else {
    $("#template-edit-id").value = "";
    $("#template-name").value = "";
    $("#template-subject-prefix").value = "Re: ";
    $("#template-body").value = "";
    $("#template-ai-instructions").value = "";
    $("#template-ai-desc").value = "";
  }
}

function closeTemplateEditor() {
  $("#template-editor").style.display = "none";
  $("#template-edit-id").value = "";
}

$("#btn-template-new").addEventListener("click", () => openTemplateEditor(null));
$("#btn-template-cancel").addEventListener("click", closeTemplateEditor);

$("#btn-template-ai-assist").addEventListener("click", async () => {
  const desc = $("#template-ai-desc").value.trim();
  if (!desc) {
    toast("Enter a description for AI assist", true);
    return;
  }
  try {
    toast("Generating with AI…");
    const result = await api("/api/templates/ai-assist", {
      method: "POST",
      body: JSON.stringify({ description: desc }),
    });
    if (result.body) $("#template-body").value = result.body;
    if (result.ai_instructions) $("#template-ai-instructions").value = result.ai_instructions;
    toast("AI draft applied");
  } catch (e) {
    toast(e.message, true);
  }
});

$("#btn-template-save").addEventListener("click", async () => {
  const name = $("#template-name").value.trim();
  if (!name) {
    toast("Template name is required", true);
    return;
  }
  const payload = {
    name,
    subject_prefix: $("#template-subject-prefix").value,
    body: $("#template-body").value,
    ai_instructions: $("#template-ai-instructions").value,
  };
  const editId = $("#template-edit-id").value;
  try {
    if (editId) {
      await api(`/api/templates/${encodeURIComponent(editId)}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      toast("Template updated");
    } else {
      await api("/api/templates", { method: "POST", body: JSON.stringify(payload) });
      toast("Template created");
    }
    closeTemplateEditor();
    await loadTemplates();
    await loadRules();
  } catch (e) {
    toast(e.message, true);
  }
});

async function deleteTemplate(id) {
  if (!confirm("Delete this template? Rules using it may break.")) return;
  try {
    await api(`/api/templates/${encodeURIComponent(id)}`, { method: "DELETE" });
    toast("Template deleted");
    await loadTemplates();
  } catch (e) {
    toast(e.message, true);
  }
}

function fillRuleTemplateSelect(selected = "") {
  const sel = $("#rule-template-id");
  if (!sel) return;
  sel.innerHTML =
    '<option value="">— select template —</option>' +
    emailSettingsState.templates
      .map(
        (t) =>
          `<option value="${escapeHtml(t.id)}" ${t.id === selected ? "selected" : ""}>${escapeHtml(t.name)}</option>`
      )
      .join("");
}

async function loadRules() {
  const data = await api("/api/rules");
  emailSettingsState.rules = data.items || [];
  renderRulesList();
}

function renderRulesList() {
  const el = $("#rules-list");
  if (!emailSettingsState.rules.length) {
    el.innerHTML = '<p class="es-empty">No rules yet. Create a template first, then add a keyword rule.</p>';
    return;
  }
  const tplMap = Object.fromEntries(emailSettingsState.templates.map((t) => [t.id, t.name]));
  el.innerHTML = emailSettingsState.rules
    .map((r) => {
      const m = r.match || {};
      const kw = [...(m.subject_keywords || []), ...(m.body_keywords || [])].slice(0, 4).join(", ");
      return `
    <div class="es-card rule-card ${r.enabled ? "" : "disabled"}" data-id="${escapeHtml(r.id)}">
      <div class="es-card-header">
        <strong>${escapeHtml(r.name)}</strong>
        <span class="badge ${r.enabled ? "ok" : "warn"}">${r.enabled ? "On" : "Off"}</span>
      </div>
      <div class="es-card-meta">
        <span>Keywords: ${escapeHtml(kw || "—")}</span>
        <span>Scope: ${escapeHtml(m.scope || "subject_or_body")}</span>
        <span>Template: ${escapeHtml(tplMap[r.template_id] || r.template_id)}</span>
        <span>${escapeHtml(r.generation)} → ${escapeHtml(r.delivery)}</span>
      </div>
      <div class="es-card-actions">
        <button class="secondary btn-rule-edit" data-id="${escapeHtml(r.id)}">Edit</button>
        <button class="secondary btn-rule-toggle" data-id="${escapeHtml(r.id)}" data-enabled="${r.enabled}">
          ${r.enabled ? "Disable" : "Enable"}
        </button>
        <button class="secondary btn-rule-delete" data-id="${escapeHtml(r.id)}">Delete</button>
      </div>
    </div>`;
    })
    .join("");

  el.querySelectorAll(".btn-rule-edit").forEach((btn) => {
    btn.addEventListener("click", () => openRuleEditor(btn.dataset.id));
  });
  el.querySelectorAll(".btn-rule-toggle").forEach((btn) => {
    btn.addEventListener("click", () => toggleRule(btn.dataset.id, btn.dataset.enabled !== "true"));
  });
  el.querySelectorAll(".btn-rule-delete").forEach((btn) => {
    btn.addEventListener("click", () => deleteRule(btn.dataset.id));
  });
}

function openRuleEditor(id) {
  const editor = $("#rule-editor");
  editor.style.display = "block";
  fillRuleTemplateSelect();
  if (id) {
    const r = emailSettingsState.rules.find((x) => x.id === id);
    if (!r) return;
    const m = r.match || {};
    $("#rule-edit-id").value = r.id;
    $("#rule-name").value = r.name || "";
    $("#rule-enabled").checked = r.enabled !== false;
    $("#rule-subject-keywords").value = formatKeywords(m.subject_keywords);
    $("#rule-body-keywords").value = formatKeywords(m.body_keywords);
    $("#rule-scope").value = m.scope || "subject_or_body";
    $("#rule-mode").value = m.mode || "any";
    fillRuleTemplateSelect(r.template_id);
    $("#rule-generation").value = r.generation || "canned";
    $("#rule-delivery").value = r.delivery || "approval";
    $("#rule-append-note").checked = r.append_to_existing_note !== false;
  } else {
    $("#rule-edit-id").value = "";
    $("#rule-name").value = "";
    $("#rule-enabled").checked = true;
    $("#rule-subject-keywords").value = "";
    $("#rule-body-keywords").value = "";
    $("#rule-scope").value = "subject_or_body";
    $("#rule-mode").value = "any";
    fillRuleTemplateSelect();
    $("#rule-generation").value = "canned";
    $("#rule-delivery").value = "approval";
    $("#rule-append-note").checked = true;
  }
}

function closeRuleEditor() {
  $("#rule-editor").style.display = "none";
  $("#rule-edit-id").value = "";
}

$("#btn-rule-new").addEventListener("click", () => {
  if (!emailSettingsState.templates.length) {
    toast("Create a template first", true);
    return;
  }
  openRuleEditor(null);
});
$("#btn-rule-cancel").addEventListener("click", closeRuleEditor);

$("#btn-rule-save").addEventListener("click", async () => {
  const name = $("#rule-name").value.trim();
  const templateId = $("#rule-template-id").value;
  if (!name || !templateId) {
    toast("Name and template are required", true);
    return;
  }
  const payload = {
    name,
    enabled: $("#rule-enabled").checked,
    match: {
      subject_keywords: parseKeywords($("#rule-subject-keywords").value),
      body_keywords: parseKeywords($("#rule-body-keywords").value),
      scope: $("#rule-scope").value,
      mode: $("#rule-mode").value,
    },
    template_id: templateId,
    generation: $("#rule-generation").value,
    delivery: $("#rule-delivery").value,
    append_to_existing_note: $("#rule-append-note").checked,
  };
  const editId = $("#rule-edit-id").value;
  try {
    if (editId) {
      await api(`/api/rules/${encodeURIComponent(editId)}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      toast("Rule updated");
    } else {
      await api("/api/rules", { method: "POST", body: JSON.stringify(payload) });
      toast("Rule created");
    }
    closeRuleEditor();
    await loadRules();
  } catch (e) {
    toast(e.message, true);
  }
});

async function toggleRule(id, enabled) {
  try {
    await api(`/api/rules/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    });
    toast(enabled ? "Rule enabled" : "Rule disabled");
    await loadRules();
  } catch (e) {
    toast(e.message, true);
  }
}

async function deleteRule(id) {
  if (!confirm("Delete this rule?")) return;
  try {
    await api(`/api/rules/${encodeURIComponent(id)}`, { method: "DELETE" });
    toast("Rule deleted");
    await loadRules();
  } catch (e) {
    toast(e.message, true);
  }
}

async function loadPollerSettings() {
  const s = await api("/api/email-settings/poller");
  $("#poller-enabled").checked = !!s.enabled;
  $("#poller-interval").value = s.interval_seconds || 300;
  const stats = [];
  if (s.last_run) stats.push(`Last run: ${s.last_run.slice(0, 19).replace("T", " ")}`);
  if (s.last_processed_count != null) stats.push(`Processed: ${s.last_processed_count}`);
  if (s.last_processed_message_id) stats.push(`Cursor: ${s.last_processed_message_id.slice(0, 12)}…`);
  $("#poller-stats").textContent = stats.join(" · ") || "No runs yet";
}

$("#btn-poller-save").addEventListener("click", async () => {
  try {
    await api("/api/email-settings/poller", {
      method: "PUT",
      body: JSON.stringify({
        enabled: $("#poller-enabled").checked,
        interval_seconds: parseInt($("#poller-interval").value, 10) || 300,
      }),
    });
    toast("Poller settings saved");
    await loadPollerSettings();
  } catch (e) {
    toast(e.message, true);
  }
});

$("#btn-process-now").addEventListener("click", async () => {
  try {
    const top = parseInt($("#process-now-top").value, 10) || 25;
    const { job_id } = await api("/api/email-settings/process-now", {
      method: "POST",
      body: JSON.stringify({ top }),
    });
    toast(`Process job started: ${job_id}`);
    pollJob(job_id, async () => {
      await loadPollerSettings();
      await loadApprovalQueue();
      await loadAutoQueue();
      await loadEmailSettingsJobs();
    });
    loadEmailSettingsJobs();
  } catch (e) {
    toast(e.message, true);
  }
});

async function loadEmailSettingsJobs() {
  const jobs = await api("/api/jobs");
  const processJobs = jobs.filter((j) => j.name === "process-inbox");
  const el = $("#email-settings-job-log");
  if (!el) return;
  el.innerHTML = processJobs.length
    ? processJobs
        .map(
          (j) =>
            `<div class="job-item"><strong>${j.name}</strong> · ${j.status} · ${j.message || j.error || ""} <span style="color:var(--muted)">${(j.finished_at || j.created_at || "").slice(0, 19)}</span></div>`
        )
        .join("")
    : "<div style='color:var(--muted)'>No process-inbox jobs yet</div>";
}

async function loadApprovalQueue() {
  const data = await api("/api/queue/approval");
  const el = $("#approval-queue");
  const items = (data.items || []).filter((i) => i.status === "pending");
  if (!items.length) {
    el.innerHTML = '<p class="es-empty">No pending approvals.</p>';
    return;
  }
  el.innerHTML = items
    .map(
      (item) => `
    <div class="queue-row" data-id="${escapeHtml(item.id)}">
      <div class="queue-row-main">
        <div class="queue-subject">${escapeHtml(item.subject || "(no subject)")}</div>
        <div class="queue-meta">
          ${escapeHtml(item.created_at?.slice(0, 19).replace("T", " ") || "")}
          · Rule: ${escapeHtml(item.rule_id)}
          · <span class="badge">${escapeHtml(item.status)}</span>
        </div>
        ${emailSettingsState.approvalPreviewId === item.id ? `<pre class="es-pre queue-preview">${escapeHtml(item.body || "")}</pre>` : ""}
      </div>
      <div class="queue-row-actions">
        <button class="secondary btn-queue-preview" data-id="${escapeHtml(item.id)}">Preview</button>
        <button class="btn-queue-approve" data-id="${escapeHtml(item.id)}">Approve</button>
        <button class="secondary btn-queue-reject" data-id="${escapeHtml(item.id)}">Reject</button>
      </div>
    </div>`
    )
    .join("");

  el.querySelectorAll(".btn-queue-preview").forEach((btn) => {
    btn.addEventListener("click", () => {
      emailSettingsState.approvalPreviewId =
        emailSettingsState.approvalPreviewId === btn.dataset.id ? null : btn.dataset.id;
      loadApprovalQueue();
    });
  });
  el.querySelectorAll(".btn-queue-approve").forEach((btn) => {
    btn.addEventListener("click", () => approveQueueEntry(btn.dataset.id));
  });
  el.querySelectorAll(".btn-queue-reject").forEach((btn) => {
    btn.addEventListener("click", () => rejectQueueEntry(btn.dataset.id));
  });
}

async function approveQueueEntry(id) {
  try {
    await api(`/api/queue/approval/${encodeURIComponent(id)}/approve`, { method: "POST" });
    toast("Approved");
    emailSettingsState.approvalPreviewId = null;
    await loadApprovalQueue();
  } catch (e) {
    toast(e.message, true);
  }
}

async function rejectQueueEntry(id) {
  try {
    await api(`/api/queue/approval/${encodeURIComponent(id)}/reject`, { method: "POST" });
    toast("Rejected");
    emailSettingsState.approvalPreviewId = null;
    await loadApprovalQueue();
  } catch (e) {
    toast(e.message, true);
  }
}

$("#btn-approval-refresh").addEventListener("click", loadApprovalQueue);

async function loadAutoQueue() {
  const data = await api("/api/queue/auto");
  const el = $("#auto-queue");
  const items = data.items || [];
  if (!items.length) {
    el.innerHTML = '<p class="es-empty">Auto queue is empty.</p>';
    return;
  }
  el.innerHTML = items
    .map(
      (item) => `
    <div class="queue-row readonly">
      <div class="queue-row-main">
        <div class="queue-subject">${escapeHtml(item.subject || "(no subject)")}</div>
        <div class="queue-meta">
          ${escapeHtml(item.created_at?.slice(0, 19).replace("T", " ") || "")}
          · ${escapeHtml(item.status)}
          ${item.thread_note ? ` · <a href="#" class="thread-note-link" data-note="${escapeHtml(item.thread_note)}">Thread note</a>` : ""}
        </div>
      </div>
    </div>`
    )
    .join("");

  el.querySelectorAll(".thread-note-link").forEach((link) => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      toast(`Thread note: ${link.dataset.note}`);
    });
  });
}

$("#btn-auto-refresh").addEventListener("click", loadAutoQueue);

// --- Knowledge base ---
async function loadKnowledgeStats() {
  const stats = await api("/api/knowledge/stats");
  $("#knowledge-stats").innerHTML = `
    <div class="card"><div class="label">Indexed emails</div><div class="value">${stats.entry_count}</div></div>
    <div class="card"><div class="label">With context</div><div class="value">${stats.with_context}</div></div>
    <div class="card"><div class="label">Approved domains</div><div class="value">${stats.approved_domain_count}</div></div>
    <div class="card"><div class="label">Approved contacts</div><div class="value">${stats.approved_contact_count}</div></div>
  `;
  const last = stats.last_sync_at ? stats.last_sync_at.slice(0, 19).replace("T", " ") : "never";
  const meta = $("#knowledge-search-meta");
  if (meta && !meta.dataset.hasQuery) {
    meta.textContent = `Last sync: ${last} · ${stats.without_context} email(s) awaiting recontextualization`;
  }
}

async function loadKnowledgeJobs() {
  const jobs = await api("/api/jobs");
  const relevant = jobs.filter((j) =>
    ["sync-knowledge", "recontextualize-knowledge"].includes(j.name)
  );
  const el = $("#knowledge-job-log");
  if (!el) return;
  el.innerHTML = relevant.length
    ? relevant
        .map(
          (j) =>
            `<div class="job-item"><strong>${j.name}</strong> · ${j.status} · ${j.message || j.error || ""} <span style="color:var(--muted)">${(j.finished_at || j.created_at || "").slice(0, 19)}</span></div>`
        )
        .join("")
    : "<div style='color:var(--muted)'>No knowledge jobs yet</div>";
}

async function loadKnowledge() {
  await loadKnowledgeStats();
  await loadKnowledgeJobs();
}

async function runKnowledgeAction(path, body) {
  try {
    const { job_id } = await api(path, { method: "POST", body: JSON.stringify(body) });
    pollJob(job_id, () => {
      loadKnowledgeStats();
      loadKnowledgeJobs();
    });
    loadKnowledgeJobs();
  } catch (e) {
    toast(e.message, true);
  }
}

$("#btn-knowledge-sync")?.addEventListener("click", () =>
  runKnowledgeAction("/api/knowledge/sync", {
    max_pages: parseInt($("#knowledge-sync-pages").value, 10) || 50,
    recontextualize_new: $("#knowledge-recontext-new").checked,
  })
);

$("#btn-knowledge-recontext")?.addEventListener("click", () =>
  runKnowledgeAction("/api/knowledge/recontextualize", {
    force: $("#knowledge-recontext-force").checked,
  })
);

async function searchKnowledge() {
  const q = $("#knowledge-search").value.trim();
  const domain = $("#knowledge-domain-filter").value.trim();
  const meta = $("#knowledge-search-meta");
  meta.dataset.hasQuery = q ? "1" : "";
  const data = await api(
    `/api/knowledge/search?q=${encodeURIComponent(q)}&domain=${encodeURIComponent(domain)}&limit=50`
  );
  meta.textContent = `${data.total} result(s)${q ? ` for “${q}”` : ""}`;
  const el = $("#knowledge-results");
  if (!data.items.length) {
    el.innerHTML = '<p class="es-empty">No matches. Sync the knowledge base first or broaden your query.</p>';
    $("#knowledge-detail").style.display = "none";
    return;
  }
  el.innerHTML = data.items
    .map(
      (item) => `
    <div class="kb-hit" data-id="${escapeHtml(item.message_id)}">
      <div class="kb-hit-subject">${escapeHtml(item.subject || "(no subject)")}</div>
      <div class="kb-hit-meta">
        ${escapeHtml(item.received_at?.slice(0, 10) || "")}
        · ${escapeHtml(item.sender_email)}
        · ${escapeHtml(item.domain_category || item.domain)}
        ${item.context?.summary ? " · summarized" : ""}
      </div>
      <div class="kb-hit-snippet">${escapeHtml(item.snippet || item.body_preview || "")}</div>
    </div>`
    )
    .join("");
  el.querySelectorAll(".kb-hit").forEach((row) => {
    row.addEventListener("click", () => showKnowledgeDetail(row.dataset.id));
  });
}

async function showKnowledgeDetail(messageId) {
  const entry = await api(`/api/knowledge/${encodeURIComponent(messageId)}`);
  const detail = $("#knowledge-detail");
  detail.style.display = "block";
  const ctx = entry.context || {};
  detail.innerHTML = `
    <button class="close-btn secondary" id="knowledge-detail-close">Close</button>
    <h3>${escapeHtml(entry.subject)}</h3>
    <p class="es-meta">${escapeHtml(entry.sender_name || entry.sender_email)} · ${escapeHtml(entry.received_at?.slice(0, 19).replace("T", " ") || "")}</p>
    ${ctx.summary ? `<p><strong>Summary:</strong> ${escapeHtml(ctx.summary)}</p>` : ""}
    ${ctx.topics?.length ? `<p><strong>Topics:</strong> ${ctx.topics.map((t) => `<span class="badge">${escapeHtml(t)}</span>`).join(" ")}</p>` : ""}
    ${ctx.action_items?.length ? `<p><strong>Action items:</strong></p><ul>${ctx.action_items.map((a) => `<li>${escapeHtml(a)}</li>`).join("")}</ul>` : ""}
    <pre class="es-pre">${escapeHtml(entry.body_text || entry.body_preview || "")}</pre>
    ${entry.web_link ? `<a href="${escapeHtml(entry.web_link)}" target="_blank" rel="noopener">Open in Outlook</a>` : ""}
  `;
  $("#knowledge-detail-close").addEventListener("click", () => {
    detail.style.display = "none";
  });
}

$("#btn-knowledge-search")?.addEventListener("click", searchKnowledge);
$("#knowledge-search")?.addEventListener(
  "keydown",
  (e) => {
    if (e.key === "Enter") searchKnowledge();
  }
);
$("#knowledge-search")?.addEventListener(
  "input",
  debounce(() => {
    if ($("#knowledge-search").value.trim().length >= 2) searchKnowledge();
  }, 400)
);

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
