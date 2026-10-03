const state = { sessionId: null, repo: null, decisions: [], dependencies: [] };
const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}

function setError(id, message = "") { $(id).textContent = message; }
function setLoading(value) { $("loading").classList.toggle("hidden", !value); }
function formatDate(value) { return value ? new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "Unknown date"; }
function escapeHtml(value) { const div = document.createElement("div"); div.textContent = value ?? ""; return div.innerHTML; }

async function checkApi() {
  try { await api("/health"); $("api-status").textContent = "API online"; }
  catch { $("api-status").textContent = "API unavailable"; $("api-status").style.color = "#b44735"; }
}

$("analyze-form").addEventListener("submit", async (event) => {
  event.preventDefault(); setError("form-error"); setLoading(true); $("workspace").classList.add("hidden");
  try {
    state.repo = await api("/api/v1/repos", { method: "POST", body: JSON.stringify({ repo_url: $("repo-url").value, max_commits: Number($("max-commits").value) }) });
    state.sessionId = state.repo.id;
    await renderWorkspace();
  } catch (error) { setError("form-error", error.message); }
  finally { setLoading(false); }
});

async function renderWorkspace() {
  $("workspace").classList.remove("hidden");
  $("repo-name").textContent = state.repo.repo_name || "Repository";
  $("repo-url-display").textContent = state.repo.repo_url;
  $("repo-url-display").href = state.repo.repo_url;
  $("commit-count").textContent = state.repo.analyzed_commits;
  $("event-count").textContent = state.repo.dependency_events.length;
  state.dependencies = state.repo.dependency_evidence || [];
  $("dependency-count").textContent = state.dependencies.length;
  renderDependencies();
  renderTimeline(await api(`/api/v1/repos/${state.sessionId}/timeline`));
  populateDependencySelect();
}

function renderDependencies() {
  const list = $("dependency-list");
  if (!state.dependencies.length) { list.innerHTML = '<p class="empty-state">No supported dependency declarations were found.</p>'; return; }
  list.innerHTML = state.dependencies.map((item) => `<div class="dependency-item" data-name="${escapeHtml(item.dependency_name)}"><div><div class="dep-name">${escapeHtml(item.dependency_name)}</div><div class="dep-meta">${escapeHtml(item.ecosystem)} · ${escapeHtml(item.declared_version || "version not declared")}</div></div><div class="dep-usage">${item.current_usage_count} file${item.current_usage_count === 1 ? "" : "s"}</div></div>`).join("");
  list.querySelectorAll(".dependency-item").forEach((item) => item.addEventListener("click", () => { $("dependency-select").value = item.dataset.name; selectDependency(); }));
}

function renderTimeline(entries) {
  const timeline = $("timeline");
  if (!entries.length) { timeline.innerHTML = '<p class="empty-state">No commits were returned.</p>'; return; }
  timeline.innerHTML = entries.map((entry) => `<div class="timeline-entry"><div class="timeline-date">${formatDate(entry.timestamp)} · ${escapeHtml(entry.author || "Unknown author")}</div><div class="timeline-message">${escapeHtml(entry.message)}</div>${entry.dependency_events.map((event) => `<span class="timeline-event">${escapeHtml(event.action)} · ${escapeHtml(event.dep_name)}</span>`).join(" ")}</div>`).join("");
}

function populateDependencySelect() {
  $("dependency-select").innerHTML = '<option value="">Choose a dependency</option>' + state.dependencies.map((item) => `<option value="${escapeHtml(item.dependency_name)}">${escapeHtml(item.dependency_name)}</option>`).join("");
  $("dependency-select").addEventListener("change", selectDependency);
  $("event-select").addEventListener("change", updateActionState);
}

function selectDependency() {
  const name = $("dependency-select").value;
  const item = state.dependencies.find((candidate) => candidate.dependency_name === name);
  $("event-select").innerHTML = '<option value="">All historical events</option>' + (item?.historical_dependency_events || []).map((event) => `<option value="${escapeHtml(event.commit_hash)}">${escapeHtml(event.commit_hash.slice(0, 10))} · ${escapeHtml(event.action)}</option>`).join("");
  $("selected-title").textContent = name ? `Why was ${name} introduced?` : "Select a dependency";
  updateActionState();
  if (name) loadInsights(name); else { $("decay-result").textContent = "Select a dependency to load current validity."; $("counterfactual-result").textContent = "Select a dependency to inspect likely impact."; }
}
function updateActionState() { $("analyze-decision").disabled = !$("dependency-select").value; }

$("analyze-decision").addEventListener("click", async () => {
  const dependency = $("dependency-select").value; if (!dependency) return;
  setError("decision-error"); $("analyze-decision").disabled = true; $("analyze-decision").textContent = "Reasoning...";
  try {
    const params = { dependency_name: dependency }; if ($("event-select").value) params.commit_hash = $("event-select").value;
    const result = await api(`/api/v1/repos/${state.sessionId}/decisions/analyze`, { method: "POST", body: JSON.stringify(params) });
    renderDecision(result);
  } catch (error) { setError("decision-error", error.message); }
  finally { $("analyze-decision").disabled = false; $("analyze-decision").innerHTML = 'Ask Gemma <span>→</span>'; }
});

function renderDecision(result) {
  $("confidence").textContent = `${result.confidence} confidence`;
  $("decision-result").classList.remove("empty-state");
  $("decision-result").innerHTML = `<div class="result-title">${escapeHtml(result.decision)}</div><div class="result-reason">${escapeHtml(result.reason)}</div><div class="evidence-list">${result.evidence.map((item) => `<div class="evidence-item"><strong>${escapeHtml(item.source_type)}:${escapeHtml(item.source_id)}</strong><br>${escapeHtml(item.claim)}</div>`).join("")}</div><div class="insight-row"><span>Current validity</span><strong>${escapeHtml(result.current_validity)}</strong></div><div class="insight-row"><span>Uncertainty</span><strong>${escapeHtml(result.uncertainty)}</strong></div>`;
}

async function loadInsights(name) {
  try {
    const [decay, counterfactual] = await Promise.all([api(`/api/v1/repos/${state.sessionId}/dependencies/${encodeURIComponent(name)}/decay`), api(`/api/v1/repos/${state.sessionId}/dependencies/${encodeURIComponent(name)}/counterfactual`)]);
    $("decay-result").innerHTML = `<div class="insight-row"><span>Historical signal</span><strong>${escapeHtml(decay.original_decision)}</strong></div><div class="insight-row"><span>Current validity</span><strong>${escapeHtml(decay.validity)}</strong></div><div class="insight-row"><span>Current files</span><strong>${decay.current_evidence.current_files.length}</strong></div><p class="empty-state">${escapeHtml(decay.uncertainty)}</p>`;
    $("counterfactual-result").innerHTML = `<div class="insight-row"><span>Likely impact</span><strong>${escapeHtml(counterfactual.likely_impact)}</strong></div><div class="insight-row"><span>Importing files</span><strong>${counterfactual.current_files.length}</strong></div><div class="insight-row"><span>Historical events</span><strong>${counterfactual.historical_events.length}</strong></div><p class="empty-state">${escapeHtml(counterfactual.uncertainty)}</p>`;
  } catch (error) { $("decay-result").textContent = error.message; $("counterfactual-result").textContent = error.message; }
}

checkApi();
