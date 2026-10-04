const state = {
  sessionId: null,
  repo: null,
  decisions: [],
  dependencies: [],
  timeline: [],
  activeTab: 'overview',
  timelineFilter: { search: '', author: '', depOnly: false },
  depFilter: { search: '', status: '' },
  depSort: { column: 'name', dir: 'asc' },
  expandedDepName: null
};

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

/* Theme Management (Light / Dark) */
function initTheme() {
  let savedTheme = null;
  try {
    savedTheme = localStorage.getItem("causalcode_theme");
  } catch {}

  if (!savedTheme) {
    savedTheme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  setTheme(savedTheme, false);
}

function setTheme(theme, save = true) {
  document.documentElement.setAttribute("data-theme", theme);
  const toggleBtn = $("theme-toggle");
  if (toggleBtn) {
    toggleBtn.textContent = theme === "dark" ? "Light mode" : "Dark mode";
  }
  if (save) {
    try {
      localStorage.setItem("causalcode_theme", theme);
    } catch {}
  }
}

$("theme-toggle")?.addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  const next = current === "dark" ? "light" : "dark";
  setTheme(next, true);
});

// Load last repo URL from localStorage on startup
try {
  const lastUrl = localStorage.getItem("causalcode_last_repo_url");
  if (lastUrl && $("repo-url")) {
    $("repo-url").value = lastUrl;
  }
} catch {}

// Example Chips Handler
document.querySelectorAll(".chip-btn").forEach((chip) => {
  chip.addEventListener("click", () => {
    const url = chip.dataset.url;
    if (url && $("repo-url")) {
      $("repo-url").value = url;
      $("repo-url").focus();
    }
  });
});

// Press '/' to focus search box
window.addEventListener("keydown", (e) => {
  if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) {
    e.preventDefault();
    let target = null;
    if (state.activeTab === "timeline") target = $("timeline-search");
    else if (state.activeTab === "dependencies") target = $("dep-search");
    else target = $("repo-url");
    target?.focus();
  }
});

// Scroll Reveal Observer for motion
function initScrollReveal() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("visible");
      }
    });
  }, { threshold: 0.1 });

  document.querySelectorAll(".workspace:not(.hidden) .panel, .tab-view:not(.hidden) .panel").forEach((panel) => {
    panel.classList.add("reveal");
    observer.observe(panel);
  });
}

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

function setLoading(value) {
  const el = $("loading");
  if (el) el.classList.toggle("hidden", !value);
}

function formatDate(value) {
  return value ? new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "Unknown date";
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}

/* Clear State & Hide Results */
function resetState() {
  state.sessionId = null;
  state.repo = null;
  state.dependencies = [];
  state.timeline = [];
  state.expandedDepName = null;

  // Hide results area completely
  $("workspace")?.classList.add("hidden");

  // Reset decision review card
  if ($("decision-result")) {
    $("decision-result").classList.add("empty-state");
    $("decision-result").textContent = "Choose a dependency to inspect its evidence and decision history.";
  }
  if ($("selected-title")) $("selected-title").textContent = "Select a dependency";
  if ($("confidence")) $("confidence").textContent = "Awaiting analysis";
  if ($("decay-result")) $("decay-result").textContent = "Select a dependency to load current validity.";
  if ($("counterfactual-result")) $("counterfactual-result").textContent = "Select a dependency to inspect likely impact.";
  if ($("decision-error")) setError("decision-error");

  // Reset stats text
  if ($("declared-count")) $("declared-count").textContent = "0";
  if ($("event-count")) $("event-count").textContent = "0";
  if ($("commit-count")) $("commit-count").textContent = "0";
  if ($("dependency-count")) $("dependency-count").textContent = "0 declared";

  $("overview-metrics-box")?.classList.add("hidden");

  // Refresh tab views if active
  if (state.activeTab === "timeline") renderFullTimeline();
  if (state.activeTab === "dependencies") renderFullDependencies();
  if (state.activeTab === "report") renderReport();
}

/* Tab Navigation Router */
function getTabFromHash() {
  const hash = window.location.hash.replace("#", "");
  return ["overview", "timeline", "dependencies", "about", "report"].includes(hash) ? hash : "overview";
}

function switchTab(tabName, updateHash = true) {
  if (!["overview", "timeline", "dependencies", "about", "report"].includes(tabName)) tabName = "overview";
  state.activeTab = tabName;

  document.querySelectorAll(".tab-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.tab === tabName);
  });

  document.querySelectorAll(".tab-view").forEach((el) => {
    el.classList.toggle("hidden", el.id !== `view-${tabName}`);
  });

  if (updateHash && window.location.hash !== `#${tabName}`) {
    history.pushState(null, "", `#${tabName}`);
  }

  if (tabName === "timeline") renderFullTimeline();
  if (tabName === "dependencies") renderFullDependencies();
  if (tabName === "report") renderReport();

  setTimeout(initScrollReveal, 50);
}

window.addEventListener("hashchange", () => switchTab(getTabFromHash(), false));
window.addEventListener("popstate", () => switchTab(getTabFromHash(), false));

document.querySelectorAll(".tab-item").forEach((link) => {
  link.addEventListener("click", (e) => {
    e.preventDefault();
    const target = link.dataset.tab;
    switchTab(target, true);
  });
});

async function checkApi() {
  const status = $("api-status");
  if (!status) return;

  try {
    await api("/health");
    status.textContent = "API online";
  } catch {
    status.textContent = "API unavailable";
    status.style.color = "#b44735";
  }
}

$("analyze-form").addEventListener("submit", async (event) => {
  event.preventDefault();

  // Clear previous errors & reset previous state first
  setError("form-error");
  resetState();

  const submitBtn = $("analyze-submit-btn");
  if (submitBtn) submitBtn.disabled = true;

  const loadingText = $("loading-text");
  if (loadingText) loadingText.textContent = "Analyzing repository...";
  setLoading(true);

  const repoUrlVal = $("repo-url").value;
  try {
    localStorage.setItem("causalcode_last_repo_url", repoUrlVal);
  } catch {}

  try {
    state.repo = await api("/api/v1/repos", {
      method: "POST",
      body: JSON.stringify({ repo_url: repoUrlVal, max_commits: Number($("max-commits").value) })
    });
    state.sessionId = state.repo.id;
    await renderWorkspace();
  } catch (error) {
    resetState();
    setError("form-error", error.message);
  } finally {
    setLoading(false);
    if (submitBtn) submitBtn.disabled = false;
  }
});

async function renderWorkspace() {
  if (!state.repo) return;

  $("workspace").classList.remove("hidden");
  $("repo-name").textContent = state.repo.repo_name || "Repository Overview";
  $("repo-url-display").textContent = state.repo.repo_url;
  $("repo-url-display").href = state.repo.repo_url;
  const overview = normalizeOverview(await api(`/api/v1/repos/${state.sessionId}/overview`));
  if ($("repo-owner")) {
    $("repo-owner").textContent = overview.repository.owner ? `by ${overview.repository.owner}` : "Owner unavailable from URL";
  }
  if ($("repo-age")) $("repo-age").textContent = overview.timeline.age_days ?? "—";
  if ($("repo-latest")) $("repo-latest").textContent = formatDate(overview.activity.latest_commit_date);
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

  // Fetch timeline entries
  state.timeline = await api(`/api/v1/repos/${state.sessionId}/timeline`);

  renderDependencies();
  renderOverviewTimeline(state.timeline);
  renderOverviewMetrics();
  populateDependencySelect();
  populateAuthorFilter();

  if (state.activeTab === "timeline") renderFullTimeline();
  if (state.activeTab === "dependencies") renderFullDependencies();
  if (state.activeTab === "report") renderReport();

  setTimeout(initScrollReveal, 100);
}

function renderOverviewMetrics() {
  const metricsBox = $("overview-metrics-box");
  const sparklineBox = $("sparkline-box");
  const commitTypesBox = $("commit-types-box");
  if (!metricsBox || !state.timeline || !state.timeline.length) {
    metricsBox?.classList.add("hidden");
    return;
  }

  // 1. Commit-activity sparkline (SVG)
  const timestamps = state.timeline.map((e) => new Date(e.timestamp).getTime()).filter((t) => !isNaN(t)).sort((a, b) => a - b);
  if (timestamps.length >= 2) {
    const minT = timestamps[0];
    const maxT = timestamps[timestamps.length - 1];
    const buckets = new Array(10).fill(0);
    const range = (maxT - minT) || 1;
    timestamps.forEach((t) => {
      let idx = Math.floor(((t - minT) / range) * 10);
      if (idx >= 10) idx = 9;
      buckets[idx]++;
    });

    const maxVal = Math.max(...buckets, 1);
    const points = buckets.map((val, idx) => {
      const x = (idx / 9) * 130 + 5;
      const y = 25 - (val / maxVal) * 20;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");

    sparklineBox.innerHTML = `
      <span class="sparkline-label">Commit Activity</span>
      <svg class="sparkline-svg" viewBox="0 0 140 28" aria-label="Commit activity sparkline">
        <polyline points="${points}" fill="none" stroke="var(--navy)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    `;
  } else {
    sparklineBox.innerHTML = "";
  }

  // 2. Commit-type breakdown
  const typeCounts = {};
  let totalTypes = 0;
  state.timeline.forEach((e) => {
    if (e.change_type) {
      const t = String(e.change_type).toLowerCase();
      typeCounts[t] = (typeCounts[t] || 0) + 1;
      totalTypes++;
    }
  });

  if (totalTypes > 0) {
    const colors = {
      feature: "var(--navy)",
      feat: "var(--navy)",
      fix: "var(--coral)",
      refactor: "var(--mint-strong)",
      deps: "#4a7c59",
      docs: "#889696",
      other: "#a0aba8"
    };

    const segments = Object.entries(typeCounts).map(([type, count]) => {
      const pct = ((count / totalTypes) * 100).toFixed(1);
      const color = colors[type] || colors.other;
      return `<div class="commit-type-segment" style="width:${pct}%; background:${color}" title="${escapeHtml(type)}: ${count} (${pct}%)"></div>`;
    }).join("");

    const legend = Object.entries(typeCounts).map(([type, count]) => {
      const color = colors[type] || colors.other;
      return `<span class="legend-item"><span class="legend-dot" style="background:${color}"></span> ${escapeHtml(type)} (${count})</span>`;
    }).join("");

    commitTypesBox.innerHTML = `
      <div class="commit-types-header"><span>Commit Type Breakdown</span><span class="tabular-nums">${totalTypes} categorized</span></div>
      <div class="commit-types-bar">${segments}</div>
      <div class="commit-types-legend">${legend}</div>
    `;
  } else {
    commitTypesBox.innerHTML = '<span class="empty-state">No commit type breakdown available in data.</span>';
  }

  metricsBox.classList.remove("hidden");
}

function renderDependencies() {
  const list = $("dependency-list");
  if (!state.dependencies.length) {
    list.innerHTML = '<p class="empty-state">No dependency manifests found in the examined commits.</p>';
    return;
  }
  list.innerHTML = state.dependencies.map((item) => `<div class="dependency-item" data-name="${escapeHtml(item.dependency_name)}"><div><div class="dep-name">${escapeHtml(item.dependency_name)}</div><div class="dep-meta">${escapeHtml(item.ecosystem)} · ${escapeHtml(item.declared_version || "version not declared")}</div></div><div class="dep-usage tabular-nums">${item.current_usage_count} file${item.current_usage_count === 1 ? "" : "s"}</div></div>`).join("");
  list.querySelectorAll(".dependency-item").forEach((item) => item.addEventListener("click", () => {
    $("dependency-select").value = item.dataset.name;
    selectDependency();
  }));
}

function renderOverviewTimeline(entries) {
  const timeline = $("timeline");
  if (!entries || !entries.length) {
    timeline.innerHTML = '<p class="empty-state">No commits found in the examined history window.</p>';
    return;
  }
  timeline.innerHTML = entries.map((entry) => `<div class="timeline-entry"><div class="timeline-date mono">${formatDate(entry.timestamp)} · ${escapeHtml(entry.author || "Unknown author")}</div><div class="timeline-message">${escapeHtml(entry.message)}</div>${(entry.dependency_events || []).map((event) => `<span class="timeline-event">${escapeHtml(event.action)} · ${escapeHtml(event.dep_name)}</span>`).join(" ")}</div>`).join("");
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
  if (name) loadInsights(name);
  else {
    $("decay-result").textContent = "Select a dependency to load current validity.";
    $("counterfactual-result").textContent = "Select a dependency to inspect likely impact.";
  }
}

function updateActionState() {
  $("analyze-decision").disabled = !$("dependency-select").value;
}

$("analyze-decision").addEventListener("click", async () => {
  const dependency = $("dependency-select").value;
  if (!dependency) return;
  setError("decision-error");
  $("analyze-decision").disabled = true;
  $("analyze-decision").textContent = "Reasoning...";
  try {
    const params = { dependency_name: dependency };
    if ($("event-select").value) params.commit_hash = $("event-select").value;
    const result = await api(`/api/v1/repos/${state.sessionId}/decisions/analyze`, { method: "POST", body: JSON.stringify(params) });
    renderDecision(result);
  } catch (error) {
    if (error.message && error.message.includes("Gemma is not configured")) {
      setNote("decision-error", "Gemma isn't set up on this server yet. Add the Gemma API key or Ollama settings in the backend .env file to enable AI explanations. Evidence below is still available.");
    } else {
      setError("decision-error", error.message);
    }
  } finally {
    $("analyze-decision").disabled = false;
    $("analyze-decision").innerHTML = 'Ask Gemma <span>→</span>';
  }
});

function renderDecision(result) {
  result = normalizeAnalysis(result);
  $("confidence").textContent = `${result.confidence} confidence`;
  $("decision-result").classList.remove("empty-state");
  $("decision-result").innerHTML = `<div class="result-title">${escapeHtml(result.decision)}</div><div class="result-reason">${escapeHtml(result.reason)}</div><div class="evidence-list">${result.evidence.map((item) => `<div class="evidence-item"><strong>${escapeHtml(item.source_type)}:${escapeHtml(item.source_id)}</strong><br>${escapeHtml(item.claim)}</div>`).join("")}</div><div class="insight-row"><span>Current validity</span><strong>${escapeHtml(result.current_validity)}</strong></div><div class="insight-row"><span>Uncertainty</span><strong>${escapeHtml(result.uncertainty)}</strong></div>`;
}

async function loadInsights(name) {
  try {
    const [decay, counterfactual] = await Promise.all([
      api(`/api/v1/repos/${state.sessionId}/dependencies/${encodeURIComponent(name)}/decay`),
      api(`/api/v1/repos/${state.sessionId}/dependencies/${encodeURIComponent(name)}/counterfactual`)
    ]);
    $("decay-result").innerHTML = `<div class="insight-row"><span>Historical signal</span><strong>${escapeHtml(decay.original_decision)}</strong></div><div class="insight-row"><span>Current validity</span><strong>${escapeHtml(decay.validity)}</strong></div><div class="insight-row"><span>Current files</span><strong class="tabular-nums">${decay.current_evidence.current_files.length}</strong></div><p class="empty-state">${escapeHtml(decay.uncertainty)}</p>`;
    $("counterfactual-result").innerHTML = `<div class="insight-row"><span>Likely impact</span><strong>${escapeHtml(counterfactual.likely_impact)}</strong></div><div class="insight-row"><span>Importing files</span><strong class="tabular-nums">${counterfactual.current_files.length}</strong></div><div class="insight-row"><span>Historical events</span><strong class="tabular-nums">${counterfactual.historical_events.length}</strong></div><p class="empty-state">${escapeHtml(counterfactual.uncertainty)}</p>`;
  } catch (error) {
    $("decay-result").textContent = error.message;
    $("counterfactual-result").textContent = error.message;
  }
}

/* Timeline View Tab Logic */
function populateAuthorFilter() {
  const select = $("timeline-author-filter");
  if (!select || !state.timeline) return;
  const authors = Array.from(new Set(state.timeline.map((e) => e.author).filter(Boolean))).sort();
  select.innerHTML = '<option value="">All authors</option>' + authors.map((a) => `<option value="${escapeHtml(a)}">${escapeHtml(a)}</option>`).join("");
}

$("timeline-search")?.addEventListener("input", (e) => {
  state.timelineFilter.search = e.target.value.toLowerCase().trim();
  renderFullTimeline();
});

$("timeline-author-filter")?.addEventListener("change", (e) => {
  state.timelineFilter.author = e.target.value;
  renderFullTimeline();
});

$("timeline-dep-filter")?.addEventListener("change", (e) => {
  state.timelineFilter.depOnly = e.target.checked;
  renderFullTimeline();
});

function renderFullTimeline() {
  const container = $("timeline-view-content");
  if (!container) return;

  if (!state.repo) {
    container.innerHTML = '<p class="empty-state">Analyze a repository from the Overview tab to see this.</p>';
    return;
  }

  if (!state.timeline || !state.timeline.length) {
    container.innerHTML = '<p class="empty-state">No commits found in the examined history window.</p>';
    return;
  }

  // Filter entries
  const filtered = state.timeline.filter((entry) => {
    if (state.timelineFilter.search) {
      const q = state.timelineFilter.search;
      const matchMsg = entry.message.toLowerCase().includes(q);
      const matchAuthor = (entry.author || "").toLowerCase().includes(q);
      const matchHash = entry.commit_hash.toLowerCase().includes(q);
      if (!matchMsg && !matchAuthor && !matchHash) return false;
    }
    if (state.timelineFilter.author && entry.author !== state.timelineFilter.author) {
      return false;
    }
    if (state.timelineFilter.depOnly && (!entry.dependency_events || !entry.dependency_events.length)) {
      return false;
    }
    return true;
  });

  if (!filtered.length) {
    container.innerHTML = '<p class="empty-state">No commits matched the selected filters.</p>';
    return;
  }

  // Group by Month Year (newest first)
  const groups = {};
  filtered.forEach((entry) => {
    const d = new Date(entry.timestamp);
    const key = d.toLocaleString("default", { month: "long", year: "numeric" });
    if (!groups[key]) groups[key] = [];
    groups[key].push(entry);
  });

  container.innerHTML = Object.entries(groups).map(([month, entries]) => `
    <div class="month-group">
      <h3 class="month-title">${escapeHtml(month)}</h3>
      ${entries.map((entry) => `
        <div class="timeline-full-row">
          <div><span class="copy-hash" data-hash="${escapeHtml(entry.commit_hash)}" title="Click to copy hash">${escapeHtml(entry.commit_hash.slice(0, 7))}</span></div>
          <div class="mono tabular-nums">${formatDate(entry.timestamp)}</div>
          <div>${escapeHtml(entry.author || "Unknown")}</div>
          <div class="commit-msg-box">
            <div>${escapeHtml(entry.message)}</div>
            ${(entry.dependency_events || []).map((ev) => `<span class="timeline-event">${escapeHtml(ev.action)} · ${escapeHtml(ev.dep_name)}</span>`).join(" ")}
          </div>
        </div>
      `).join("")}
    </div>
  `).join("");

  // Add Copy Hash event listeners
  container.querySelectorAll(".copy-hash").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const hash = btn.dataset.hash;
      navigator.clipboard.writeText(hash).then(() => {
        const originalText = btn.textContent;
        btn.textContent = "Copied";
        setTimeout(() => { btn.textContent = originalText; }, 1500);
      }).catch(() => {});
    });
  });
}

/* Dependencies View Tab Logic */
function getDepStatus(item) {
  if (item.current_usage_detected) return "active";
  if ((item.historical_dependency_events || []).some((e) => e.action === "removed")) return "removed";
  return "unused";
}

function renderLifespanChart() {
  const container = $("lifespan-chart-container");
  if (!container) return;

  if (!state.dependencies || !state.dependencies.length) {
    container.classList.add("hidden");
    return;
  }

  const now = Date.now();
  const validDeps = [];
  let skippedCount = 0;

  state.dependencies.forEach((item) => {
    const events = item.historical_dependency_events || [];
    let startT = null;
    let endT = now;

    if (events.length > 0) {
      const times = events.map((e) => new Date(e.timestamp || e.commit_timestamp || 0).getTime()).filter((t) => t > 0);
      if (times.length > 0) startT = Math.min(...times);
      const removedEvent = events.find((e) => e.action === "removed");
      if (removedEvent) {
        const rmTime = new Date(removedEvent.timestamp || 0).getTime();
        if (rmTime > 0) endT = rmTime;
      }
    }

    if (!startT && state.timeline && state.timeline.length > 0) {
      const match = state.timeline.find((entry) => (entry.dependency_events || []).some((ev) => ev.dep_name?.toLowerCase() === item.dependency_name.toLowerCase()));
      if (match) startT = new Date(match.timestamp).getTime();
    }

    if (startT && !isNaN(startT)) {
      validDeps.push({ item, startT, endT });
    } else {
      skippedCount++;
    }
  });

  if (!validDeps.length) {
    container.innerHTML = `
      <div class="lifespan-header"><h3 class="lifespan-title">Dependency Lifespan Chart</h3></div>
      <p class="lifespan-note">Skipped ${skippedCount} dependencies with no historical date evidence in analyzed commits.</p>
    `;
    container.classList.remove("hidden");
    return;
  }

  const minTime = Math.min(...validDeps.map((d) => d.startT));
  const maxTime = Math.max(...validDeps.map((d) => d.endT), now);
  const timeSpan = (maxTime - minTime) || 1;

  const rowsHtml = validDeps.slice(0, 15).map(({ item, startT, endT }) => {
    const leftPct = Math.max(0, Math.min(95, ((startT - minTime) / timeSpan) * 100));
    const widthPct = Math.max(3, Math.min(100 - leftPct, ((endT - startT) / timeSpan) * 100));
    const status = getDepStatus(item);
    const barClass = status === "unused" ? "coral" : "navy";

    return `
      <div class="lifespan-row">
        <span class="lifespan-name" title="${escapeHtml(item.dependency_name)}">${escapeHtml(item.dependency_name)}</span>
        <div class="lifespan-track">
          <div class="lifespan-bar ${barClass}" style="left:${leftPct.toFixed(1)}%; width:${widthPct.toFixed(1)}%;" title="${escapeHtml(item.dependency_name)} (${formatDate(startT)} to ${status === "removed" ? formatDate(endT) : "HEAD"})"></div>
        </div>
      </div>
    `;
  }).join("");

  container.innerHTML = `
    <div class="lifespan-header">
      <h3 class="lifespan-title">Dependency Lifespan Chart</h3>
    </div>
    <div class="lifespan-grid">
      ${rowsHtml}
    </div>
    <div class="lifespan-axis mono">
      <span>${formatDate(minTime)}</span>
      <span>${formatDate(maxTime)}</span>
    </div>
    ${skippedCount > 0 ? `<p class="lifespan-note">Skipped ${skippedCount} dependencies with no historical date evidence in analyzed commits.</p>` : ""}
  `;

  container.classList.remove("hidden");
}

$("dep-search")?.addEventListener("input", (e) => {
  state.depFilter.search = e.target.value.toLowerCase().trim();
  renderFullDependencies();
});

$("dep-status-filter")?.addEventListener("change", (e) => {
  state.depFilter.status = e.target.value;
  renderFullDependencies();
});

function renderFullDependencies() {
  const container = $("dep-view-content");
  if (!container) return;

  if (!state.repo) {
    container.innerHTML = '<p class="empty-state">Analyze a repository from the Overview tab to see this.</p>';
    $("lifespan-chart-container")?.classList.add("hidden");
    return;
  }

  if (!state.dependencies || !state.dependencies.length) {
    container.innerHTML = '<p class="empty-state">No dependency manifests found in the examined commits.</p>';
    $("lifespan-chart-container")?.classList.add("hidden");
    return;
  }

  renderLifespanChart();

  // Filter
  let list = state.dependencies.filter((item) => {
    const status = getDepStatus(item);
    if (state.depFilter.status && status !== state.depFilter.status) return false;
    if (state.depFilter.search) {
      const q = state.depFilter.search;
      const matchName = item.dependency_name.toLowerCase().includes(q);
      const matchEco = item.ecosystem.toLowerCase().includes(q);
      const matchVer = (item.declared_version || "").toLowerCase().includes(q);
      if (!matchName && !matchEco && !matchVer) return false;
    }
    return true;
  });

  // Sort
  const { column, dir } = state.depSort;
  list.sort((a, b) => {
    let valA, valB;
    if (column === "name") { valA = a.dependency_name; valB = b.dependency_name; }
    else if (column === "ecosystem") { valA = a.ecosystem; valB = b.ecosystem; }
    else if (column === "version") { valA = a.declared_version || ""; valB = b.declared_version || ""; }
    else if (column === "files") { valA = a.current_files ? a.current_files.length : 0; valB = b.current_files ? b.current_files.length : 0; }
    else if (column === "status") { valA = getDepStatus(a); valB = getDepStatus(b); }

    if (valA < valB) return dir === "asc" ? -1 : 1;
    if (valA > valB) return dir === "asc" ? 1 : -1;
    return 0;
  });

  if (!list.length) {
    container.innerHTML = '<p class="empty-state">No dependencies matched the selected filters.</p>';
    return;
  }

  const sortIndicator = (col) => (state.depSort.column === col ? (state.depSort.dir === "asc" ? " ↑" : " ↓") : "");

  container.innerHTML = `
    <div class="table-responsive">
      <table class="dep-table">
        <thead>
          <tr>
            <th data-sort="name" class="${column === "name" ? "sorted" : ""}">Name${sortIndicator("name")}</th>
            <th data-sort="ecosystem" class="${column === "ecosystem" ? "sorted" : ""}">Ecosystem${sortIndicator("ecosystem")}</th>
            <th data-sort="version" class="${column === "version" ? "sorted" : ""}">Version${sortIndicator("version")}</th>
            <th data-sort="files" class="${column === "files" ? "sorted" : ""}">Files importing it${sortIndicator("files")}</th>
            <th data-sort="status" class="${column === "status" ? "sorted" : ""}">Status${sortIndicator("status")}</th>
          </tr>
        </thead>
        <tbody>
          ${list.map((item) => {
            const status = getDepStatus(item);
            const isExpanded = state.expandedDepName === item.dependency_name;
            const fileCount = item.current_files ? item.current_files.length : item.current_usage_count;
            const firstEvent = (item.historical_dependency_events && item.historical_dependency_events.length > 0) ? item.historical_dependency_events[0] : null;

            return `
              <tr class="dep-row ${isExpanded ? "expanded" : ""}" data-name="${escapeHtml(item.dependency_name)}">
                <td><strong>${escapeHtml(item.dependency_name)}</strong></td>
                <td>${escapeHtml(item.ecosystem)}</td>
                <td class="mono tabular-nums">${escapeHtml(item.declared_version || "Not declared")}</td>
                <td class="tabular-nums">${fileCount} file${fileCount === 1 ? "" : "s"}</td>
                <td><span class="status-pill ${status}">${status}</span></td>
              </tr>
              ${isExpanded ? `
                <tr class="dep-detail-tr">
                  <td colspan="5">
                    <div class="dep-detail-box">
                      <div class="dep-detail-grid">
                        <div class="dep-detail-card">
                          <h4>First Appearance</h4>
                          <p>${firstEvent ? `${escapeHtml(firstEvent.action)} in <span class="copy-hash" data-hash="${escapeHtml(firstEvent.commit_hash)}">${escapeHtml(firstEvent.commit_hash.slice(0, 7))}</span> (${escapeHtml(firstEvent.version || "version not declared")})` : "No historical event recorded in commit window"}</p>
                        </div>
                        <div class="dep-detail-card">
                          <h4>Importing Files (${item.current_files ? item.current_files.length : 0})</h4>
                          ${item.current_files && item.current_files.length ? `<ul>${item.current_files.map((f) => `<li><code>${escapeHtml(f)}</code></li>`).join("")}</ul>` : '<p class="empty-state">No imports found at HEAD</p>'}
                        </div>
                        <div class="dep-detail-card">
                          <h4>Evidence Commits</h4>
                          ${item.historical_dependency_events && item.historical_dependency_events.length ? `<ul>${item.historical_dependency_events.map((e) => `<li><span class="copy-hash" data-hash="${escapeHtml(e.commit_hash)}">${escapeHtml(e.commit_hash.slice(0, 7))}</span> ${escapeHtml(e.action)} (${escapeHtml(e.manifest_file)})</li>`).join("")}</ul>` : '<p class="empty-state">No historical events recorded</p>'}
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              ` : ""}
            `;
          }).join("")}
        </tbody>
      </table>
    </div>
  `;

  // Sort listeners
  container.querySelectorAll("th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const col = th.dataset.sort;
      if (state.depSort.column === col) {
        state.depSort.dir = state.depSort.dir === "asc" ? "desc" : "asc";
      } else {
        state.depSort.column = col;
        state.depSort.dir = "asc";
      }
      renderFullDependencies();
    });
  });

  // Row expand listeners
  container.querySelectorAll(".dep-row").forEach((row) => {
    row.addEventListener("click", () => {
      const name = row.dataset.name;
      state.expandedDepName = state.expandedDepName === name ? null : name;
      renderFullDependencies();
    });
  });

  // Copy Hash listeners
  container.querySelectorAll(".copy-hash").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const hash = btn.dataset.hash;
      navigator.clipboard.writeText(hash).then(() => {
        const originalText = btn.textContent;
        btn.textContent = "Copied";
        setTimeout(() => { btn.textContent = originalText; }, 1500);
      }).catch(() => {});
    });
  });
}

/* Report Tab Logic & Downloads */
function renderReport() {
  const container = $("report-content");
  if (!container) return;

  if (!state.repo) {
    container.innerHTML = '<p class="empty-state">Analyze a repository from the Overview tab to see this.</p>';
    return;
  }

  const unusedCount = state.dependencies.filter((d) => getDepStatus(d) === "unused").length;
  const activeCount = state.dependencies.filter((d) => getDepStatus(d) === "active").length;
  const removedCount = state.dependencies.filter((d) => getDepStatus(d) === "removed").length;

  container.innerHTML = `
    <div class="report-section">
      <h3>Repository Summary</h3>
      <table class="report-meta-table">
        <tr><td>Repository URL</td><td><a href="${escapeHtml(state.repo.repo_url)}" target="_blank" rel="noreferrer">${escapeHtml(state.repo.repo_url)}</a></td></tr>
        <tr><td>Commits Examined</td><td class="tabular-nums">${state.repo.analyzed_commits}</td></tr>
        <tr><td>Total Declared Dependencies</td><td class="tabular-nums">${state.dependencies.length}</td></tr>
        <tr><td>Active Dependencies (Imported)</td><td class="tabular-nums">${activeCount}</td></tr>
        <tr><td>Unused Dependencies (Declared, Not Imported)</td><td class="tabular-nums">${unusedCount}</td></tr>
        <tr><td>Removed Dependencies</td><td class="tabular-nums">${removedCount}</td></tr>
        <tr><td>Dependency Changes (Events)</td><td class="tabular-nums">${state.repo.dependency_events.length}</td></tr>
      </table>
    </div>

    <div class="report-section">
      <h3>Declared Dependencies Inventory</h3>
      ${state.dependencies.length ? `
        <table class="dep-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Ecosystem</th>
              <th>Version</th>
              <th>Files Importing</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            ${state.dependencies.map((d) => {
              const status = getDepStatus(d);
              const files = d.current_files ? d.current_files.length : d.current_usage_count;
              return `
                <tr>
                  <td><strong>${escapeHtml(d.dependency_name)}</strong></td>
                  <td>${escapeHtml(d.ecosystem)}</td>
                  <td class="mono">${escapeHtml(d.declared_version || "Not declared")}</td>
                  <td class="tabular-nums">${files}</td>
                  <td><span class="status-pill ${status}">${status}</span></td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      ` : '<p class="empty-state">No dependency manifests found in the examined commits.</p>'}
    </div>
  `;
}

$("download-json-btn")?.addEventListener("click", () => {
  if (!state.repo) return;
  const reportObj = {
    repository: state.repo.repo_url,
    analyzed_commits: state.repo.analyzed_commits,
    stats: {
      declared_dependencies: state.dependencies.length,
      active_dependencies: state.dependencies.filter((d) => getDepStatus(d) === "active").length,
      unused_dependencies: state.dependencies.filter((d) => getDepStatus(d) === "unused").length,
      dependency_change_events: state.repo.dependency_events.length
    },
    dependencies: state.dependencies.map((d) => ({
      name: d.dependency_name,
      ecosystem: d.ecosystem,
      declared_version: d.declared_version,
      status: getDepStatus(d),
      importing_files: d.current_files || []
    })),
    timeline_summary: state.timeline ? state.timeline.slice(0, 20) : []
  };

  const blob = new Blob([JSON.stringify(reportObj, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `causalcode-report-${state.repo.repo_name || "repo"}.json`;
  a.click();
  URL.revokeObjectURL(url);
});

$("download-md-btn")?.addEventListener("click", () => {
  if (!state.repo) return;
  const activeCount = state.dependencies.filter((d) => getDepStatus(d) === "active").length;
  const unusedCount = state.dependencies.filter((d) => getDepStatus(d) === "unused").length;

  let md = `# CausalCode Repository Analysis Report\n\n`;
  md += `- **Repository:** ${state.repo.repo_url}\n`;
  md += `- **Commits Examined:** ${state.repo.analyzed_commits}\n`;
  md += `- **Declared Dependencies:** ${state.dependencies.length}\n`;
  md += `- **Active Dependencies:** ${activeCount}\n`;
  md += `- **Unused Dependencies:** ${unusedCount}\n\n`;

  md += `## Declared Dependencies Inventory\n\n`;
  md += `| Name | Ecosystem | Version | Files Importing | Status |\n`;
  md += `| --- | --- | --- | --- | --- |\n`;
  state.dependencies.forEach((d) => {
    const status = getDepStatus(d);
    const files = d.current_files ? d.current_files.length : d.current_usage_count;
    md += `| ${d.dependency_name} | ${d.ecosystem} | ${d.declared_version || "Not declared"} | ${files} | ${status} |\n`;
  });

  const blob = new Blob([md], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `causalcode-report-${state.repo.repo_name || "repo"}.md`;
  a.click();
  URL.revokeObjectURL(url);
});

// Initializations
initTheme();
switchTab(getTabFromHash(), false);
checkApi();
