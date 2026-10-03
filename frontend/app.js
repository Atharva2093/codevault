const state = { sessionId: null, repo: null, decisions: [], dependencies: [], issues: [], currentIssueNumber: null };
const $ = (id) => document.getElementById(id);
const asArray = (value) => Array.isArray(value) ? value : [];
const asObject = (value) => value && typeof value === "object" ? value : {};

function normalizeOverview(value) {
  const overview = asObject(value);
  return {
    ...overview,
    repository: asObject(overview.repository),
    timeline: asObject(overview.timeline),
    activity: asObject(overview.activity),
    technologies: asArray(overview.technologies),
    structure: asArray(overview.structure),
    contributors: asArray(overview.contributors),
    history: asArray(overview.history).map((entry) => ({
      ...asObject(entry),
      dependency_events: asArray(entry?.dependency_events),
    })),
  };
}

function normalizeIssue(value) {
  const issue = asObject(value);
  return { ...issue, labels: asArray(issue.labels) };
}

function normalizeAnalysis(value) {
  const result = asObject(value);
  return {
    ...result,
    facts: asArray(result.facts),
    reasoning: asArray(result.reasoning),
    relevant_technologies: asArray(result.relevant_technologies),
    required_skills: asArray(result.required_skills),
    suggested_first_steps: asArray(result.suggested_first_steps),
    relevant_history: asArray(result.relevant_history),
    relevant_skills: asArray(result.relevant_skills),
    evidence: asArray(result.evidence),
  };
}

function assertFrontendNormalization() {
  const overview = normalizeOverview({});
  const analysis = normalizeAnalysis({});
  if (![overview.technologies, overview.structure, overview.contributors, overview.history].every(Array.isArray)) {
    throw new Error("Frontend overview normalization failed");
  }
  if (![normalizeIssue({}).labels, analysis.facts, analysis.reasoning, analysis.evidence].every(Array.isArray)) {
    throw new Error("Frontend response normalization failed");
  }
}

assertFrontendNormalization();

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
  const overview = normalizeOverview(await api(`/api/v1/repos/${state.sessionId}/overview`));
  $("repo-owner").textContent = overview.repository.owner ? `by ${overview.repository.owner}` : "Owner unavailable from URL";
  $("repo-age").textContent = overview.timeline.age_days ?? "—";
  $("repo-latest").textContent = formatDate(overview.activity.latest_commit_date);
  $("commit-count").textContent = state.repo.analyzed_commits;
  const dependencyEvents = asArray(state.repo.dependency_events);
  $("event-count").textContent = dependencyEvents.length;
  if ($("event-count-label")) {
    $("event-count-label").textContent = `dependency changes in last ${state.repo.analyzed_commits} commits`;
  }
  state.dependencies = asArray(state.repo.dependency_evidence);
  if ($("declared-count")) {
    $("declared-count").textContent = state.dependencies.length;
  }
  $("dependency-count").textContent = `${state.dependencies.length} declared`;
  renderDependencies();
  renderTechnology(overview.technologies);
  renderStructure(overview.structure);
  renderContributors(overview.contributors);
  renderTimeline(overview.history);
  renderSynopsisEvidence(overview);
  await loadIssues();
  populateDependencySelect();
  await loadStoredSynopsis();
}

function renderSynopsisEvidence(overview) {
  const timeline = overview.timeline ?? {};
  const activity = overview.activity ?? {};
  const technologies = asArray(overview.technologies).map((item) => item.name).filter(Boolean);
  $("synopsis-evidence").innerHTML = `<strong>Evidence used</strong><span>Repository: ${escapeHtml(overview.repository?.owner || "unknown")}/${escapeHtml(overview.repository?.name || "unknown")}</span><span>Technologies: ${escapeHtml(technologies.join(", ") || "none detected")}</span><span>Commits examined: ${activity.analyzed_commit_count ?? 0}</span><span>Contributors: ${activity.unique_contributor_count ?? 0}</span><span>First commit: ${escapeHtml(formatDate(timeline.first_commit))}</span><span>Latest commit: ${escapeHtml(formatDate(timeline.latest_commit))}</span>`;
}

async function loadIssues() {
  setError("issues-error");
  $("issue-count").textContent = "Loading";
  $("issues-list").innerHTML = '<p class="empty-state">Fetching open issues...</p>';
  try {
    const issues = asArray(await api(`/api/v1/repos/${state.sessionId}/issues`)).map(normalizeIssue);
    state.issues = issues;
    $("issue-count").textContent = `${issues.length} open`;
    const list = $("issues-list");
    if (!issues.length) { list.innerHTML = '<p class="empty-state">No open issues found</p>'; return; }
    list.innerHTML = issues.map((issue) => `<article class="issue-card"><div class="issue-card-head"><strong>#${issue.number}</strong><span>${escapeHtml(issue.author)}</span></div><h4>${escapeHtml(issue.title)}</h4><p>${escapeHtml((issue.body || "No description provided.").slice(0, 220))}</p><div class="issue-labels">${issue.labels.map((label) => `<span>${escapeHtml(label)}</span>`).join("")}</div><div class="issue-actions"><a href="${escapeHtml(issue.html_url)}" target="_blank" rel="noreferrer">View on GitHub</a><button class="issue-analyze-button" data-issue="${issue.number}">Analyze Issue <span>→</span></button></div></article>`).join("");
    list.querySelectorAll(".issue-analyze-button").forEach((button) => button.addEventListener("click", () => loadIssueAnalysis(button.dataset.issue)));
  } catch (error) {
    state.issues = [];
    $("issue-count").textContent = "Unavailable";
    setError("issues-error", "Unable to load issues");
    $("issues-list").innerHTML = '<p class="empty-state">Unable to load issues</p>';
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
  result = normalizeAnalysis(result);
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
  result = normalizeAnalysis(result);
  $("guidance-recommendation").textContent = escapeHtml((result.recommendation || "Unavailable").replaceAll("_", " "));
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
  state.dependencies = asArray(state.dependencies);
  if (!state.dependencies.length) { list.innerHTML = '<p class="empty-state">Select a dependency to inspect its evidence and decision history.</p>'; return; }
  list.innerHTML = state.dependencies.map((item) => `<div class="dependency-item" data-name="${escapeHtml(item.dependency_name)}"><div><div class="dep-name">${escapeHtml(item.dependency_name)}</div><div class="dep-meta">${escapeHtml(item.ecosystem)} · ${escapeHtml(item.declared_version || "version not declared")}</div></div><div class="dep-usage">${item.current_usage_count} file${item.current_usage_count === 1 ? "" : "s"}</div></div>`).join("");
  list.querySelectorAll(".dependency-item").forEach((item) => item.addEventListener("click", () => { $("dependency-select").value = item.dataset.name; selectDependency(); }));
}

function renderTimeline(entries) {
  entries = asArray(entries);
  const timeline = $("timeline");
  if (!entries.length) { timeline.innerHTML = '<p class="empty-state">Not enough repository history for archaeology</p>'; return; }
  timeline.innerHTML = entries.map((entry) => {
    const dependencyEvents = asArray(entry.dependency_events);
    return `<div class="timeline-entry"><div class="timeline-date">${formatDate(entry.timestamp)} · ${escapeHtml(entry.author || "Unknown author")}</div><div class="timeline-message">${escapeHtml(entry.message)}</div>${dependencyEvents.map((event) => `<span class="timeline-event">${escapeHtml(event.action)} · ${escapeHtml(event.dep_name)}</span>`).join(" ")}<button class="archaeology-button" data-commit="${escapeHtml(entry.sha)}">Why this change?</button></div>`;
  }).join("");
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
  result = normalizeAnalysis(result);
  $("archaeology-title").textContent = `Why did ${commitSha.slice(0, 10)} change?`;
  $("archaeology-confidence").textContent = `${result.confidence} confidence`;
  $("archaeology-result").className = "archaeology-result";
  const facts = result.facts.map((fact) => `<div class="archaeology-item fact"><strong>FACT</strong><span>${escapeHtml(fact)}</span></div>`).join("");
  const reasoning = result.reasoning.map((item) => `<div class="archaeology-item inference"><strong>INFERENCE</strong><span>${escapeHtml(item)}</span></div>`).join("");
  const evidence = result.evidence.map((item) => `<div class="evidence-item"><strong>${escapeHtml(item.source_type)}:${escapeHtml(item.source_id)}</strong><br>${escapeHtml(item.claim)}</div>`).join("");
  $("archaeology-result").innerHTML = `<div class="result-title">${escapeHtml(result.what_changed)}</div><div class="archaeology-reason"><strong>Likely reason</strong><p>${escapeHtml(result.likely_reason)}</p></div><div class="archaeology-items">${facts}${reasoning}</div><div class="archaeology-reason uncertainty"><strong>UNCERTAINTY</strong><p>${escapeHtml(result.uncertainty)}</p></div><div class="evidence-list">${evidence}</div>`;
}

function renderTechnology(items) {
  items = asArray(items);
  $("technology-list").innerHTML = items.length ? items.map((item) => `<div class="fact-row"><strong>${escapeHtml(item.name)}</strong><span>${item.file_count} files</span></div>`).join("") : '<p class="empty-state">No recognized source files.</p>';
}

function renderStructure(items) {
  items = asArray(items);
  $("structure-list").innerHTML = items.length ? items.map((item) => `<span class="structure-chip">${escapeHtml(item)}</span>`).join("") : '<p class="empty-state">No top-level structure found.</p>';
}

function renderContributors(items) {
  items = asArray(items);
  $("contributor-list").innerHTML = items.length ? items.map((item) => `<div class="contributor-row"><span class="avatar">${escapeHtml((item.name || "?").slice(0, 1).toUpperCase())}</span><div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.email)}</small></div></div>`).join("") : '<p class="empty-state">No contributors found in analyzed history.</p>';
}

function populateDependencySelect() {
  state.dependencies = asArray(state.dependencies);
  $("dependency-select").innerHTML = '<option value="">Choose a dependency</option>' + state.dependencies.map((item) => `<option value="${escapeHtml(item.dependency_name)}">${escapeHtml(item.dependency_name)}</option>`).join("");
  $("dependency-select").addEventListener("change", selectDependency);
  $("event-select").addEventListener("change", updateActionState);
}

function selectDependency() {
  const name = $("dependency-select").value;
  const item = state.dependencies.find((candidate) => candidate.dependency_name === name);
  const historicalEvents = asArray(item?.historical_dependency_events);
  $("event-select").innerHTML = '<option value="">All historical events</option>' + historicalEvents.map((event) => `<option value="${escapeHtml(event.commit_hash)}">${escapeHtml((event.commit_hash || "").slice(0, 10))} · ${escapeHtml(event.action)}</option>`).join("");
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
  result = normalizeAnalysis(result);
  $("confidence").textContent = `${result.confidence} confidence`;
  $("decision-result").classList.remove("empty-state");
  $("decision-result").innerHTML = `<div class="result-title">${escapeHtml(result.decision)}</div><div class="result-reason">${escapeHtml(result.reason)}</div><div class="evidence-list">${result.evidence.map((item) => `<div class="evidence-item"><strong>${escapeHtml(item.source_type)}:${escapeHtml(item.source_id)}</strong><br>${escapeHtml(item.claim)}</div>`).join("")}</div><div class="insight-row"><span>Current validity</span><strong>${escapeHtml(result.current_validity)}</strong></div><div class="insight-row"><span>Uncertainty</span><strong>${escapeHtml(result.uncertainty)}</strong></div>`;
}

async function loadInsights(name) {
  try {
    const [decay, counterfactual] = await Promise.all([api(`/api/v1/repos/${state.sessionId}/dependencies/${encodeURIComponent(name)}/decay`), api(`/api/v1/repos/${state.sessionId}/dependencies/${encodeURIComponent(name)}/counterfactual`)]);
    const decayData = asObject(decay);
    const counterfactualData = asObject(counterfactual);
    const currentEvidence = asObject(decayData.current_evidence);
    const currentFiles = asArray(currentEvidence.current_files);
    const importingFiles = asArray(counterfactualData.current_files);
    const historicalEvents = asArray(counterfactualData.historical_events);
    $("decay-result").innerHTML = `<div class="insight-row"><span>Historical signal</span><strong>${escapeHtml(decayData.original_decision)}</strong></div><div class="insight-row"><span>Current validity</span><strong>${escapeHtml(decayData.validity)}</strong></div><div class="insight-row"><span>Current files</span><strong>${currentFiles.length}</strong></div><p class="empty-state">${escapeHtml(decayData.uncertainty)}</p>`;
    $("counterfactual-result").innerHTML = `<div class="insight-row"><span>Likely impact</span><strong>${escapeHtml(counterfactualData.likely_impact)}</strong></div><div class="insight-row"><span>Importing files</span><strong>${importingFiles.length}</strong></div><div class="insight-row"><span>Historical events</span><strong>${historicalEvents.length}</strong></div><p class="empty-state">${escapeHtml(counterfactualData.uncertainty)}</p>`;
  } catch (error) { $("decay-result").textContent = error.message; $("counterfactual-result").textContent = error.message; }
}

async function loadStoredSynopsis() {
  try { renderSynopsis(await api(`/api/v1/repos/${state.sessionId}/synopsis`)); }
  catch { $("synopsis-result").textContent = "No synopsis generated for this repository yet."; }
}

function renderSynopsis(result) {
  $("synopsis-status").textContent = result.ai_status === "FAILED" ? "AI reasoning failed" : "AI reasoning complete";
  $("synopsis-result").classList.remove("empty-state");
  $("synopsis-result").innerHTML = `<div class="synopsis-purpose">${escapeHtml(result.purpose)}</div><p>${escapeHtml(result.what_it_does)}</p><div class="synopsis-columns"><div><span>Evolution</span><strong>${escapeHtml(result.project_evolution_summary)}</strong></div><div><span>Current state</span><strong>${escapeHtml(result.current_state_summary)}</strong></div><div><span>Confidence</span><strong>${escapeHtml(result.confidence)}</strong></div><div><span>Uncertainty</span><strong>${escapeHtml(result.uncertainty)}</strong></div></div>`;
}

$("generate-synopsis").addEventListener("click", async () => {
  const button = $("generate-synopsis"); button.disabled = true; button.innerHTML = "Gemma reasoning..."; $("synopsis-status").textContent = "AI reasoning running";
  try { renderSynopsis(await api(`/api/v1/repos/${state.sessionId}/synopsis`, { method: "POST" })); }
  catch (error) { $("synopsis-status").textContent = error.message.includes("timed out") ? "AI reasoning timed out" : "AI reasoning failed"; setError("form-error", error.message); }
  finally { button.disabled = false; button.innerHTML = 'Ask Gemma <span>→</span>'; }
});

checkApi();
