const state = { sessionId: null, repo: null, decisions: [], dependencies: [], issues: [], currentIssueNumber: null };
const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}

function setError(id, message = "") {
  const el = $(id);
  if (!el) return;
  el.textContent = message;
  el.classList.remove("muted-note");
}

function setNote(id, message = "") {
  const el = $(id);
  if (!el) return;
  el.textContent = message;
  el.classList.add("muted-note");
}

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
  const overview = await api(`/api/v1/repos/${state.sessionId}/overview`);
  $("repo-owner").textContent = overview.repository.owner ? `by ${overview.repository.owner}` : "Owner unavailable from URL";
  $("repo-age").textContent = overview.timeline.age_days ?? "—";
  $("repo-latest").textContent = formatDate(overview.activity.latest_commit_date);
  $("commit-count").textContent = state.repo.analyzed_commits;
  $("event-count").textContent = state.repo.dependency_events.length;
  if ($("event-count-label")) {
    $("event-count-label").textContent = `dependency changes in last ${state.repo.analyzed_commits} commits`;
  }
  state.dependencies = state.repo.dependency_evidence || [];
  if ($("declared-count")) {
    $("declared-count").textContent = state.dependencies.length;
  }
  $("dependency-count").textContent = `${state.dependencies.length} declared`;
  renderDependencies();
  renderTechnology(overview.technologies);
  renderStructure(overview.structure);
  renderContributors(overview.contributors);
  renderTimeline(overview.history);
  await loadIssues();
  populateDependencySelect();
  await loadStoredSynopsis();
}

async function loadIssues() {
  setError("issues-error");
  try {
    const issues = await api(`/api/v1/repos/${state.sessionId}/issues`);
    state.issues = issues;
    $("issue-count").textContent = `${issues.length} open`;
    const list = $("issues-list");
    if (!issues.length) { list.innerHTML = '<p class="empty-state">No open issues were found.</p>'; return; }
    list.innerHTML = issues.map((issue) => `<article class="issue-card"><div class="issue-card-head"><strong>#${issue.number}</strong><span>${escapeHtml(issue.author)}</span></div><h4>${escapeHtml(issue.title)}</h4><p>${escapeHtml((issue.body || "No description provided.").slice(0, 220))}</p><div class="issue-labels">${issue.labels.map((label) => `<span>${escapeHtml(label)}</span>`).join("")}</div><div class="issue-actions"><a href="${escapeHtml(issue.html_url)}" target="_blank" rel="noreferrer">View on GitHub</a><button class="issue-analyze-button" data-issue="${issue.number}">Analyze Issue <span>→</span></button></div></article>`).join("");
    list.querySelectorAll(".issue-analyze-button").forEach((button) => button.addEventListener("click", () => loadIssueAnalysis(button.dataset.issue)));
  } catch (error) {
    $("issue-count").textContent = "Unavailable";
    setError("issues-error", error.message);
    $("issues-list").innerHTML = '<p class="empty-state">Open issues could not be loaded.</p>';
  }
}

async function loadIssueAnalysis(issueNumber) {
  state.currentIssueNumber = Number(issueNumber);
  const panel = $("issue-analysis-panel");
  panel.classList.remove("hidden");
  setError("issue-analysis-error");
  $("issue-complexity").textContent = "Reading evidence...";
  $("issue-analysis-result").className = "archaeology-result empty-state";
  $("issue-analysis-result").textContent = "Gemma is comparing the issue with repository technologies and history.";
  try {
    const result = await api(`/api/v1/repos/${state.sessionId}/issues/${encodeURIComponent(issueNumber)}/analysis`);
    renderIssueAnalysis(result);
  } catch (error) {
    setError("issue-analysis-error", error.message);
    $("issue-complexity").textContent = "Unavailable";
  }
}

function renderIssueAnalysis(result) {
  $("issue-analysis-title").textContent = `Issue #${result.issue_number}`;
  $("issue-complexity").textContent = `${result.estimated_complexity} complexity`;
  $("start-here").classList.remove("hidden");
  $("issue-analysis-result").className = "archaeology-result";
  const facts = result.facts.map((fact) => `<div class="archaeology-item fact"><strong>FACT</strong><span>${escapeHtml(fact)}</span></div>`).join("");
  const reasoning = result.reasoning.map((item) => `<div class="archaeology-item inference"><strong>INFERENCE</strong><span>${escapeHtml(item)}</span></div>`).join("");
  const technologies = result.relevant_technologies.map((item) => `<span class="structure-chip">${escapeHtml(item)}</span>`).join("");
  const skills = result.required_skills.map((item) => `<span class="structure-chip">${escapeHtml(item)}</span>`).join("");
  const evidence = result.evidence.map((item) => `<div class="evidence-item"><strong>${escapeHtml(item.source_type)}:${escapeHtml(item.source_id)}</strong><br>${escapeHtml(item.claim)}</div>`).join("");
  const issue = state.issues.find((item) => item.number === result.issue_number);
  const githubLink = issue ? `<a class="github-issue-link" href="${escapeHtml(issue.html_url)}" target="_blank" rel="noreferrer">Open Issue on GitHub</a>` : "";
  $("issue-analysis-result").innerHTML = `<div class="result-title">${escapeHtml(result.summary)}</div><div class="archaeology-reason"><strong>Problem</strong><p>${escapeHtml(result.problem)}</p></div><div class="archaeology-reason"><strong>Likely affected area</strong><p>${escapeHtml(result.likely_affected_area)}</p></div><div class="issue-analysis-tags"><div><strong>Technologies</strong><div>${technologies || '<span class="empty-state">Insufficient evidence</span>'}</div></div><div><strong>Required skills</strong><div>${skills || '<span class="empty-state">Insufficient evidence</span>'}</div></div></div><div class="archaeology-items">${facts}${reasoning}</div><div class="archaeology-reason uncertainty"><strong>UNCERTAINTY</strong><p>${escapeHtml(result.uncertainty)}</p></div><div class="evidence-list">${evidence}</div>${githubLink}`;
}

$("start-here").addEventListener("click", loadGuidance);

async function loadGuidance() {
  if (!state.currentIssueNumber) return;
  const panel = $("guidance-panel");
  panel.classList.remove("hidden");
  setError("guidance-error");
  $("guidance-recommendation").textContent = "Reading analysis...";
  $("guidance-result").className = "archaeology-result empty-state";
  $("guidance-result").textContent = "Gemma is turning the validated issue analysis into practical first steps.";
  try {
    const result = await api(`/api/v1/repos/${state.sessionId}/issues/${state.currentIssueNumber}/guidance`);
    renderGuidance(result);
  } catch (error) {
    setError("guidance-error", error.message);
    $("guidance-recommendation").textContent = "Unavailable";
  }
}

function renderGuidance(result) {
  $("guidance-recommendation").textContent = escapeHtml(result.recommendation.replaceAll("_", " "));
  $("guidance-result").className = "archaeology-result";
  const facts = result.facts.map((fact) => `<div class="archaeology-item fact"><strong>FACT</strong><span>${escapeHtml(fact)}</span></div>`).join("");
  const reasoning = result.reasoning.map((item) => `<div class="archaeology-item inference"><strong>INFERENCE</strong><span>${escapeHtml(item)}</span></div>`).join("");
  const steps = result.suggested_first_steps.map((step, index) => `<li>${index + 1}. ${escapeHtml(step)}</li>`).join("");
  const history = result.relevant_history.map((item) => `<span class="structure-chip">${escapeHtml(item)}</span>`).join("");
  const skills = result.relevant_skills.map((item) => `<span class="structure-chip">${escapeHtml(item)}</span>`).join("");
  const technologies = result.relevant_technologies.map((item) => `<span class="structure-chip">${escapeHtml(item)}</span>`).join("");
  const evidence = result.evidence.map((item) => `<div class="evidence-item"><strong>${escapeHtml(item.source_type)}:${escapeHtml(item.source_id)}</strong><br>${escapeHtml(item.claim)}</div>`).join("");
  const issue = state.issues.find((item) => item.number === result.issue_number);
  const githubLink = issue ? `<a class="github-issue-link" href="${escapeHtml(issue.html_url)}" target="_blank" rel="noreferrer">Open Issue on GitHub</a>` : "";
  $("guidance-result").innerHTML = `<div class="result-title">${escapeHtml(result.why_this_issue)}</div><div class="issue-analysis-tags"><div><strong>Relevant skills</strong><div>${skills || '<span class="empty-state">Insufficient evidence</span>'}</div></div><div><strong>Relevant technologies</strong><div>${technologies || '<span class="empty-state">Insufficient evidence</span>'}</div></div></div><div class="archaeology-reason"><strong>Affected area</strong><p>${escapeHtml(result.affected_area)}</p></div><div class="archaeology-reason"><strong>Before you start</strong><ol>${steps || '<li>Insufficient evidence</li>'}</ol></div><div class="archaeology-reason"><strong>Relevant history</strong><div class="guidance-history">${history || '<span class="empty-state">No matching repository history found</span>'}</div></div><div class="archaeology-items">${facts}${reasoning}</div><div class="archaeology-reason uncertainty"><strong>UNCERTAINTY</strong><p>${escapeHtml(result.uncertainty)}</p></div><div class="evidence-list">${evidence}</div>${githubLink}`;
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
  timeline.innerHTML = entries.map((entry) => `<div class="timeline-entry"><div class="timeline-date">${formatDate(entry.timestamp)} · ${escapeHtml(entry.author || "Unknown author")}</div><div class="timeline-message">${escapeHtml(entry.message)}</div>${entry.dependency_events.map((event) => `<span class="timeline-event">${escapeHtml(event.action)} · ${escapeHtml(event.dep_name)}</span>`).join(" ")}<button class="archaeology-button" data-commit="${escapeHtml(entry.sha)}">Why this change?</button></div>`).join("");
  timeline.querySelectorAll(".archaeology-button").forEach((button) => button.addEventListener("click", () => loadArchaeology(button.dataset.commit)));
}

async function loadArchaeology(commitSha) {
  setError("archaeology-error");
  $("archaeology-confidence").textContent = "Reading evidence...";
  $("archaeology-result").className = "archaeology-result empty-state";
  $("archaeology-result").textContent = "Gemma is comparing the selected commit with its repository context.";
  try {
    const result = await api(`/api/v1/repos/${state.sessionId}/commits/${encodeURIComponent(commitSha)}/archaeology`);
    renderArchaeology(result, commitSha);
  } catch (error) {
    setError("archaeology-error", error.message);
    $("archaeology-confidence").textContent = "Unavailable";
  }
}

function renderArchaeology(result, commitSha) {
  $("archaeology-title").textContent = `Why did ${commitSha.slice(0, 10)} change?`;
  $("archaeology-confidence").textContent = `${result.confidence} confidence`;
  $("archaeology-result").className = "archaeology-result";
  const facts = result.facts.map((fact) => `<div class="archaeology-item fact"><strong>FACT</strong><span>${escapeHtml(fact)}</span></div>`).join("");
  const reasoning = result.reasoning.map((item) => `<div class="archaeology-item inference"><strong>INFERENCE</strong><span>${escapeHtml(item)}</span></div>`).join("");
  const evidence = result.evidence.map((item) => `<div class="evidence-item"><strong>${escapeHtml(item.source_type)}:${escapeHtml(item.source_id)}</strong><br>${escapeHtml(item.claim)}</div>`).join("");
  $("archaeology-result").innerHTML = `<div class="result-title">${escapeHtml(result.what_changed)}</div><div class="archaeology-reason"><strong>Likely reason</strong><p>${escapeHtml(result.likely_reason)}</p></div><div class="archaeology-items">${facts}${reasoning}</div><div class="archaeology-reason uncertainty"><strong>UNCERTAINTY</strong><p>${escapeHtml(result.uncertainty)}</p></div><div class="evidence-list">${evidence}</div>`;
}

function renderTechnology(items) {
  $("technology-list").innerHTML = items.length ? items.map((item) => `<div class="fact-row"><strong>${escapeHtml(item.name)}</strong><span>${item.file_count} files</span></div>`).join("") : '<p class="empty-state">No recognized source files.</p>';
}

function renderStructure(items) {
  $("structure-list").innerHTML = items.length ? items.map((item) => `<span class="structure-chip">${escapeHtml(item)}</span>`).join("") : '<p class="empty-state">No top-level structure found.</p>';
}

function renderContributors(items) {
  $("contributor-list").innerHTML = items.length ? items.map((item) => `<div class="contributor-row"><span class="avatar">${escapeHtml((item.name || "?").slice(0, 1).toUpperCase())}</span><div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.email)}</small></div></div>`).join("") : '<p class="empty-state">No contributors found in analyzed history.</p>';
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
  } catch (error) {
    if (error.message && error.message.includes("Gemma is not configured")) {
      setNote("decision-error", "Gemma isn't set up on this server yet. Add the Gemma API key or Ollama settings in the backend .env file to enable AI explanations. Evidence below is still available.");
    } else {
      setError("decision-error", error.message);
    }
  }
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

async function loadStoredSynopsis() {
  try { renderSynopsis(await api(`/api/v1/repos/${state.sessionId}/synopsis`)); }
  catch { $("synopsis-result").textContent = "No synopsis generated for this repository yet."; }
}

function renderSynopsis(result) {
  $("synopsis-result").classList.remove("empty-state");
  $("synopsis-result").innerHTML = `<div class="synopsis-purpose">${escapeHtml(result.purpose)}</div><p>${escapeHtml(result.what_it_does)}</p><div class="synopsis-columns"><div><span>Evolution</span><strong>${escapeHtml(result.project_evolution_summary)}</strong></div><div><span>Current state</span><strong>${escapeHtml(result.current_state_summary)}</strong></div><div><span>Confidence</span><strong>${escapeHtml(result.confidence)}</strong></div><div><span>Uncertainty</span><strong>${escapeHtml(result.uncertainty)}</strong></div></div>`;
}

$("generate-synopsis").addEventListener("click", async () => {
  const button = $("generate-synopsis"); button.disabled = true; button.innerHTML = "Reading evidence...";
  try { renderSynopsis(await api(`/api/v1/repos/${state.sessionId}/synopsis`, { method: "POST" })); }
  catch (error) { setError("form-error", error.message); }
  finally { button.disabled = false; button.innerHTML = 'Generate synopsis <span>→</span>'; }
});

checkApi();
