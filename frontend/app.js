"use strict";
// All content from the API (including scraped prospect text) is rendered with textContent, never innerHTML.
const $ = (s, r = document) => r.querySelector(s);
const h = (tag, attrs, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return e;
};
async function api(path, method = "GET", body) {
  const r = await fetch("/api" + path, { method, headers: { "content-type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}
let toastTimer;
function toast(msg, kind = "") {
  const t = $("#toast"); t.textContent = msg; t.className = "toast " + kind; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), 7000);
}
async function busy(btn, label, fn) {
  const old = btn.textContent; btn.disabled = true; btn.textContent = label;
  try { return await fn(); } catch (e) { toast(e.message, "bad"); } finally { btn.disabled = false; btn.textContent = old; }
}
function handle(out) { // surface queued tasks clearly instead of failing silently
  if (out && out.status === "queued") toast(out.message + " (" + out.error + ")", "warn");
  return out;
}

// ---------- generic safe JSON renderer ----------
function show(v) {
  if (v == null || v === "") return h("span", { class: "muted" }, "none");
  if (Array.isArray(v)) return v.length ? h("ul", { class: "l" }, v.map((x) => h("li", {}, typeof x === "object" ? show(x) : String(x)))) : h("span", { class: "muted" }, "none");
  if (typeof v === "object") return h("dl", { class: "kv" }, Object.entries(v).filter(([k]) => k !== "model").flatMap(([k, x]) => [h("dt", {}, k.replace(/_/g, " ")), h("dd", {}, show(x))]));
  return String(v);
}

// ---------- shell: status chips, tape, rail ----------
const VIEWS = { setup: "Business and products", pipeline: "Prospect pipeline", replies: "Replies", trace: "Local trace" };
const S = { view: "setup", businesses: [], productId: null, prospectId: null };

function rail() {
  const r = $("#rail"); r.replaceChildren();
  for (const [k, label] of Object.entries(VIEWS)) r.append(h("button", { "aria-current": S.view === k, onclick: () => { S.view = k; render(); } }, label));
}
const chip = (dot, text, title) => h("span", { class: "chip", title: title || "" }, h("i", { class: "dot " + dot }), text);
async function status() {
  try {
    const s = await api("/status");
    const o = s.ollama, c = $("#chips"); c.replaceChildren();
    if (!o.up) c.append(chip("bad", "Ollama not running", "Start it with: ollama serve. AI steps will be queued; no cloud fallback is used."));
    else if (!s.model_installed) c.append(chip("warn", "Model missing: " + s.model, "Run: ollama pull " + s.model));
    else c.append(chip("ok", "Ollama up, " + s.model));
    c.append(chip(s.queue.pending ? "warn" : "ok", "Queue " + s.queue.pending));
    c.append(chip(s.strict_local ? "ok" : "warn", s.strict_local ? "Network sealed" : "Network guard off", s.blocked_connections + " blocked connection attempts"));
    c.append(chip(s.embedder.startsWith("sentence") ? "ok" : "warn", "Embeddings: " + (s.embedder.startsWith("sentence") ? "sentence-transformers" : "hashing fallback"), s.embedder_fallback_reason));
    const li = s.last_inference, t = $("#tape"); t.replaceChildren();
    if (!li) t.append(h("span", {}, "No local inference yet. Every model call will appear here with its endpoint and token counts."));
    else t.append(h("b", {}, li.model), "\u2192 " + li.endpoint.replace("http://", ""), li.task, li.latency_ms + " ms", li.prompt_tokens + " in / " + li.completion_tokens + " out tokens", li.ok ? "" : h("span", { class: "warn" }, "failed"), h("span", { class: "sealed" }, "localhost only"));
  } catch (e) { $("#chips").replaceChildren(chip("bad", "Backend unreachable")); }
}

// ---------- Setup view ----------
async function setupView(m) {
  S.businesses = await api("/businesses");
  m.append(h("h1", {}, "Business and products"), h("p", { class: "muted" }, "Describe your company and each product. The local model builds a profile from your documents and a separate ICP for every product."));
  if (!S.businesses.length) m.append(h("div", { class: "empty" }, h("p", {}, "No business yet. Load the synthetic sample company to try the full workflow, or add your own below."),
    h("button", { class: "btn", onclick: (e) => busy(e.target, "Loading", async () => { await api("/demo/seed", "POST"); render(); }) }, "Load sample data")));
  for (const b of S.businesses) {
    const card = h("section", { class: "card" }, h("div", { class: "row" }, h("h2", {}, b.name), b.is_sample ? h("span", { class: "pill" }, "synthetic sample") : null),
      h("p", { class: "muted small" }, `Sender persona: ${b.persona_name}, ${b.persona_role}. Stored documents: ${b.has_docs ? b.docs_chars + " characters" : "none"}.`),
      h("div", { class: "row" },
        h("button", { class: "btn ghost small", onclick: (e) => busy(e.target, "Loading", async () => { const r = await api(`/businesses/${b.id}/docs`, "POST", { load_folder: true }); toast("Stored " + r.chars + " characters from data/company_docs"); render(); }) }, "Load documents from data folder"),
        h("button", { class: "btn small", onclick: (e) => busy(e.target, "Generating", async () => { handle(await api(`/businesses/${b.id}/profile`, "POST")); render(); }) }, "Generate business profile")),
      b.profile ? h("div", {}, h("h3", {}, "Business profile"), show(b.profile)) : h("p", { class: "muted small" }, "No profile yet."));
    m.append(card);
    const grid = h("div", { class: "grid2" });
    for (const p of b.products) grid.append(h("section", { class: "card" }, h("h2", {}, p.name), h("p", {}, p.description),
      h("p", { class: "muted small" }, `${p.pricing || "No pricing"} | ${p.prospect_count} prospects`),
      h("button", { class: "btn small", onclick: (e) => busy(e.target, "Generating", async () => { handle(await api(`/products/${p.id}/icp`, "POST")); render(); }) }, p.icp ? "Regenerate ICP" : "Generate ICP"),
      p.icp ? h("div", {}, h("h3", {}, "Ideal customer profile"), show(p.icp)) : h("p", { class: "muted small" }, "No ICP yet.")));
    m.append(grid, productForm(b));
  }
  m.append(businessForm());
}
function field(label, el) { return h("div", {}, h("label", {}, label), el); }
function businessForm() {
  const n = h("input", { required: true }), w = h("input"), pn = h("input", { value: "Alex" }), pr = h("input", { value: "Business Development" }), d = h("textarea", { placeholder: "Paste company information, or load documents after saving." });
  return h("details", { class: "card" }, h("summary", {}, "Add your own business"), field("Company name", n), field("Website", w), field("Sender name", pn), field("Sender role", pr), field("Company information", d),
    h("p", {}, h("button", { class: "btn small", onclick: (e) => busy(e.target, "Saving", async () => { await api("/businesses", "POST", { name: n.value, website: w.value, persona_name: pn.value, persona_role: pr.value, raw_docs: d.value }); render(); }) }, "Save business")));
}
function productForm(b) {
  const n = h("input"), d = h("textarea"), pr = h("input"), be = h("textarea", { placeholder: "One benefit per line" }), cta = h("input", { value: "15-minute call" });
  return h("details", { class: "card" }, h("summary", {}, "Add a product to " + b.name), field("Product name", n), field("What it does and who it is for", d), field("Pricing", pr), field("Key benefits", be), field("Call to action", cta),
    h("p", {}, h("button", { class: "btn small", onclick: (e) => busy(e.target, "Saving", async () => { await api("/products", "POST", { business_id: b.id, name: n.value, description: d.value, pricing: pr.value, benefits: be.value.split("\n").filter(Boolean), cta: cta.value }); render(); }) }, "Save product")));
}

// ---------- Pipeline view ----------
const STAGES = [["research", "Research"], ["signals", "Signals"], ["problem", "Problem"], ["score", "Score"], ["email", "Email"]];
async function pipelineView(m) {
  S.businesses = await api("/businesses");
  const prods = S.businesses.flatMap((b) => b.products.map((p) => ({ ...p, biz: b.name })));
  m.append(h("h1", {}, "Prospect pipeline"));
  if (!prods.length) return m.append(h("div", { class: "empty" }, "Add a business and product first (Business and products)."));
  if (!prods.find((p) => p.id === S.productId)) S.productId = prods[0].id;
  const sel = h("select", { onchange: () => { S.productId = +sel.value; S.prospectId = null; render(); } }, prods.map((p) => h("option", { value: p.id, selected: p.id === S.productId }, `${p.name} (${p.biz})`)));
  const prod = prods.find((p) => p.id === S.productId);
  const list = await api(`/products/${S.productId}/prospects`);
  const prog = h("span", { class: "muted small" });
  const file = h("input", { type: "file", accept: ".json", hidden: true, onchange: async () => { const items = JSON.parse(await file.files[0].text()); await api(`/products/${S.productId}/prospects/import`, "POST", { prospects: items }); render(); } });
  m.append(h("div", { class: "row card" }, h("div", {}, h("label", {}, "Product"), sel),
    h("button", { class: "btn", onclick: (e) => busy(e.target, "Running", async () => {
      if (!prod.icp) { toast("Generate the ICP for this product first.", "warn"); return; }
      let i = 0; for (const p of list) { prog.textContent = `Prospect ${++i} of ${list.length}: ${p.name}`; const r = await api(`/prospects/${p.id}/run-all`, "POST"); if (r.steps.some((s) => s.status === "queued")) { toast("Local model unavailable: remaining work queued.", "warn"); break; } }
      prog.textContent = ""; render(); }) }, "Run all stages for all prospects"),
    h("button", { class: "btn ghost", onclick: () => file.click() }, "Import prospects (JSON)"), file, prog));
  if (!list.length) return m.append(h("div", { class: "empty" }, "No prospects for this product yet. Import a JSON file, or load the sample data."));
  const rows = list.map((p) => h("tr", { class: "click" + (p.id === S.prospectId ? " pick" : ""), onclick: () => { S.prospectId = p.id; render(); } },
    h("td", {}, h("b", {}, p.name), h("div", { class: "muted small" }, `${p.title}, ${p.company}`)),
    h("td", {}, p.score_data ? [h("span", { class: "tier " + p.tier }, p.tier), " ", p.score.toFixed(0), p.score_data.partial ? h("span", { class: "warn small" }, " partial") : ""] : h("span", { class: "muted" }, p.status))));
  const split = h("div", { class: "split" }, h("div", { class: "card" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Prospect"), h("th", {}, "Score"))), h("tbody", {}, rows))), h("div", { id: "detail" }));
  m.append(split);
  if (S.prospectId) await detail($("#detail"), S.prospectId);
  else $("#detail").append(h("div", { class: "empty" }, "Select a prospect to see its research, signals, score and email."));
}
async function detail(el, id) {
  const p = await api(`/prospects/${id}`);
  const done = { research: p.research_data, signals: p.signals_data, problem: p.problem_data, score: p.score_data, email: p.emails.length };
  const run = (st) => async (e) => busy(e.target, "Running", async () => { const r = handle(await api(`/prospects/${id}/${st}`, "POST")); if (r.status === "done") toast(st + " done"); render(); });
  el.append(h("div", { class: "card" }, h("h2", {}, p.name), h("p", { class: "muted" }, `${p.title}, ${p.company} | ${p.industry} | ${p.employees ?? "?"} employees | ${p.location}`),
    h("p", { class: "muted small" }, `Source: ${p.source || "unknown"}`),
    h("ol", { class: "steps" }, STAGES.map(([k, label]) => h("li", { class: done[k] ? "done" : "" }, label, " ", h("button", { class: "btn ghost small", onclick: run(k) }, done[k] ? "Redo" : "Run")))),
    h("div", { class: "row" }, h("button", { class: "btn small", onclick: (e) => busy(e.target, "Running", async () => { handle(await api(`/prospects/${id}/run-all`, "POST")); render(); }) }, "Run all stages"),
      h("button", { class: "btn ghost small", onclick: async () => { const u = prompt("Public page URL to fetch (needs internet; no AI is used for fetching):"); if (u) { try { const r = await api(`/prospects/${id}/fetch-web`, "POST", { url: u }); toast("Stored " + r.chars + " characters from " + r.title); render(); } catch (e) { toast(e.message, "bad"); } } } }, "Fetch from web (online only)"))));
  if (p.research_data) { const r = p.research_data; el.append(h("div", { class: "card" }, h("h3", {}, "Research"), show({ summary: r.company_summary, offerings: r.offerings, tools_mentioned: r.tools_mentioned, recent_events: r.recent_events, pain_hints: r.pain_hints }), h("h3", {}, "Verified evidence"), show(r.evidence), r.evidence_rejected && r.evidence_rejected.length ? h("p", { class: "warn small" }, r.evidence_rejected.length + " quote(s) rejected because they were not found in the source text.") : null)); }
  if (p.signals_data) el.append(h("div", { class: "card" }, h("h3", {}, "Buying signals"), p.signals_data.signals.length ? h("table", {}, h("tbody", {}, p.signals_data.signals.map((s) => h("tr", {}, h("td", {}, h("span", { class: "pill" }, s.type.replace(/_/g, " "))), h("td", {}, "strength " + s.strength), h("td", {}, s.evidence, s.evidence_verified ? "" : h("div", { class: "warn small" }, "Evidence not found in source: strength capped.")))))) : h("p", { class: "muted" }, "No real signals found in the text.")));
  if (p.problem_data) el.append(h("div", { class: "card" }, h("h3", {}, "Problem statement"), show(p.problem_data)));
  if (p.score_data) { const s = p.score_data; el.append(h("div", { class: "card" }, h("h3", {}, "Score " + s.score + " (tier " + s.tier + ")"), s.partial ? h("p", { class: "warn" }, "Partial: the local model was unavailable, so this uses rules, embeddings and signals only. The model fit is queued.") : null,
    h("table", {}, h("tbody", {}, Object.entries(s.components).map(([k, v]) => h("tr", {}, h("td", {}, k.replace("_", " ")), h("td", {}, h("div", { class: "bar" }, h("i", { style: `width:${Math.round(v * 100)}%` }))), h("td", {}, Math.round(v * 100) + "%"), h("td", { class: "muted small" }, "weight " + s.weights[k]))))),
    s.llm_fit ? h("p", {}, h("b", {}, "Model fit " + s.llm_fit.fit_score + "/10: "), s.llm_fit.reasoning) : null, h("p", { class: "muted small" }, "Embedder: " + s.embedder + " | cosine " + s.cosine))); }
  if (p.emails.length) { const e = p.emails[0]; el.append(h("div", { class: "card" }, h("h3", {}, "Email draft (not sent; Harvey Local has no sending)"), h("p", {}, h("b", {}, "Subject: " + e.subject)), h("div", { class: "email" }, e.body),
    h("p", { class: "muted small" }, "Model: " + e.model + " | checks: " + (JSON.parse(e.checks_json).issues.join("; ") || "all passed")), h("button", { class: "btn ghost small", onclick: () => navigator.clipboard.writeText(e.subject + "\n\n" + e.body).then(() => toast("Copied")) }, "Copy"))); }
}

// ---------- Replies view ----------
async function repliesView(m) {
  const t = h("textarea", { placeholder: "Paste a prospect's reply, for example: Not right now, try again in September." }), out = h("div");
  m.append(h("h1", {}, "Reply classification"), h("p", { class: "muted" }, "Opt-outs and auto-replies are caught by fixed rules, so they work even when the model is offline. Everything else is classified by the local model."),
    h("div", { class: "card" }, field("Prospect reply", t), h("div", { class: "row" },
      h("button", { class: "btn", onclick: (e) => busy(e.target, "Classifying", async () => { const r = handle(await api("/replies/classify", "POST", { text: t.value })); out.replaceChildren(r.reply.label ? replyCard(r.reply) : h("p", { class: "warn" }, "Queued until Ollama is running.")); }) }, "Classify reply"),
      h("button", { class: "btn ghost", onclick: (e) => busy(e.target, "Running samples", async () => { const r = await api("/replies/eval-sample", "POST"); out.replaceChildren(evalTable(r)); }) }, "Run the 12 sample conversations")), out));
  const hist = await api("/replies");
  m.append(h("div", { class: "card" }, h("h3", {}, "Recent classifications"), hist.length ? h("table", {}, h("tbody", {}, hist.slice(0, 15).map((r) => h("tr", {}, h("td", {}, r.text.slice(0, 90)), h("td", {}, r.label ? h("span", { class: "pill" }, r.label.replace(/_/g, " ")) : "queued"), h("td", { class: "muted small" }, r.method || ""))))) : h("p", { class: "muted" }, "Nothing classified yet.")));
}
const replyCard = (r) => h("div", { class: "card" }, h("p", {}, h("span", { class: "pill" }, r.label.replace(/_/g, " ")), " confidence " + Math.round(r.confidence * 100) + "% via " + r.method), h("p", {}, r.rationale), h("p", {}, h("b", {}, "Suggested action: "), r.suggested_action), r.suggested_reply ? h("div", { class: "email" }, r.suggested_reply) : null);
function evalTable(r) {
  if (r.error) return h("p", { class: "bad" }, r.error + ` (${r.completed}/${r.total} done)`);
  return h("div", {}, h("h3", {}, `Accuracy ${Math.round(r.accuracy * 100)}% (${r.correct}/${r.total})`),
    h("table", {}, h("thead", {}, h("tr", {}, ["Reply", "Expected", "Predicted", "Via"].map((x) => h("th", {}, x)))), h("tbody", {}, r.results.map((x) => h("tr", {}, h("td", {}, x.text.slice(0, 80)), h("td", {}, x.expected), h("td", { class: x.correct ? "ok" : "bad" }, x.predicted), h("td", { class: "muted small" }, x.method))))));
}

// ---------- Trace view ----------
async function traceView(m) {
  const [hw, mod, q, log, st] = await Promise.all([api("/hardware"), api("/models"), api("/queue"), api("/inference-log?limit=40"), api("/status")]);
  const r = hw.recommendation, d = hw.hardware;
  m.append(h("h1", {}, "Local trace"), h("p", { class: "muted" }, "Proof that inference runs on this machine: hardware, installed models and licences, queued work, and every model call."));
  m.append(h("div", { class: "grid2" },
    h("div", { class: "card" }, h("h3", {}, "Hardware and model choice"), show({ ram: `${d.ram_total_gb} GB total, ${d.ram_available_gb} GB free`, cpu: `${d.cpu_physical} cores (${d.cpu_logical} threads)`, gpu: d.gpus.length ? d.gpus.map((g) => `${g.name} ${g.vram_gb} GB`) : (d.apple_silicon ? "Apple silicon (unified memory)" : "none detected"), recommended: `${r.model} (${r.profile})`, why: r.reason, notes: r.notes }),
      h("p", { class: "small muted" }, "Active model: " + st.model + (st.model_installed ? "" : ". Not installed; run: ollama pull " + st.model))),
    h("div", { class: "card" }, h("h3", {}, "Installed models and licences"), mod.ollama_up ? (mod.installed.length ? h("table", {}, h("tbody", {}, mod.installed.map((x) => h("tr", {}, h("td", {}, x.model), h("td", { class: "muted small" }, x.license_header))))) : h("p", { class: "muted" }, "No models installed.")) : h("p", { class: "bad" }, "Ollama is not running."))));
  m.append(h("div", { class: "card" }, h("div", { class: "row" }, h("h3", {}, `Queue: ${q.counts.pending} pending, ${q.counts.done} done, ${q.counts.failed} failed`),
    h("button", { class: "btn small", onclick: (e) => busy(e.target, "Processing", async () => { const r = await api("/queue/process", "POST"); toast(r.reason ? "Not processed: " + r.reason : `Processed ${r.processed}`, r.reason ? "warn" : ""); render(); }) }, "Process queue now")),
    q.tasks.length ? h("table", {}, h("tbody", {}, q.tasks.slice(0, 10).map((t) => h("tr", {}, h("td", {}, t.kind), h("td", {}, t.status), h("td", { class: "muted small" }, t.error.slice(0, 120)))))) : h("p", { class: "muted" }, "Queue is empty.")));
  m.append(h("div", { class: "card" }, h("h3", {}, "Inference log (latest 40)"), log.length ? h("table", {}, h("thead", {}, h("tr", {}, ["Time", "Task", "Model", "Endpoint", "Tokens in/out", "ms", "OK"].map((x) => h("th", {}, x)))),
    h("tbody", {}, log.map((x) => h("tr", {}, h("td", {}, new Date(x.ts * 1000).toLocaleTimeString()), h("td", {}, x.task), h("td", {}, x.model), h("td", { class: "small" }, x.endpoint.replace("http://", "")), h("td", {}, x.prompt_tokens + "/" + x.completion_tokens), h("td", {}, x.latency_ms), h("td", { class: x.ok ? "ok" : "bad" }, x.ok ? "yes" : "no" + (x.error ? ": " + x.error.slice(0, 60) : ""))))) ) : h("p", { class: "muted" }, "No inference yet.")));
}

async function render() {
  rail(); const m = $("#main"); m.replaceChildren();
  try { await ({ setup: setupView, pipeline: pipelineView, replies: repliesView, trace: traceView })[S.view](m); } catch (e) { m.append(h("p", { class: "bad" }, e.message)); }
  status();
}
render(); setInterval(status, 6000);
