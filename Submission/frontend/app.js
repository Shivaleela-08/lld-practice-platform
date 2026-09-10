const API = "/api";
const LEARNER_ID = "default";

const viewPractice = document.getElementById("view-practice");
const viewHistory = document.getElementById("view-history");
const tabPractice = document.getElementById("tab-practice");
const tabHistory = document.getElementById("tab-history");

let pollTimer = null;

// -- tabs -------------------------------------------------------------

tabPractice.onclick = () => switchTab("practice");
tabHistory.onclick = () => switchTab("history");

function switchTab(name) {
  clearInterval(pollTimer);
  const isPractice = name === "practice";
  viewPractice.style.display = isPractice ? "block" : "none";
  viewHistory.style.display = isPractice ? "none" : "block";
  tabPractice.classList.toggle("active", isPractice);
  tabHistory.classList.toggle("active", !isPractice);
  if (isPractice) renderProblemList();
  else renderHistory();
}

// -- API helpers --------------------------------------------------------

async function api(path, opts) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed: ${res.status}`);
  return data;
}

// -- Practice: problem list ----------------------------------------------

async function renderProblemList() {
  viewPractice.innerHTML = "<p>Loading problems...</p>";
  const { problems } = await api("/problems");
  viewPractice.innerHTML = problems.map(p => `
    <div class="card">
      <h3>${p.title} <span class="badge ${p.difficulty.toLowerCase()}">${p.difficulty}</span></h3>
      <p>${p.summary}</p>
      <ul class="req-list">${p.requirements.map(r => `<li>${r}</li>`).join("")}</ul>
      <button class="primary" data-id="${p.id}">Start attempt</button>
    </div>
  `).join("");
  viewPractice.querySelectorAll("button[data-id]").forEach(btn => {
    btn.onclick = () => startAttempt(btn.dataset.id);
  });
}

async function startAttempt(problemId) {
  const attempt = await api("/attempts", {
    method: "POST",
    body: JSON.stringify({ problem_id: problemId, learner_id: LEARNER_ID }),
  });
  const problem = await api(`/problems/${problemId}`);
  renderAttemptWorkspace(attempt, problem);
}

function renderAttemptWorkspace(attempt, problem) {
  viewPractice.innerHTML = `
    <div class="card">
      <h3>${problem.title}</h3>
      <p class="hint">Design in whatever level of detail you'd bring to an interview: classes, responsibilities, key relationships, and how it satisfies each requirement.</p>
      <label>Format:
        <select id="format">
          <option value="TEXT_DESIGN">Text design</option>
          <option value="CODE">Code</option>
          <option value="DIAGRAM_TEXT">Diagram (text/UML)</option>
        </select>
      </label>
      <br /><br />
      <textarea id="content" placeholder="Write your design here..."></textarea>
      <br /><br />
      <button class="primary" id="submit-btn">Submit for feedback</button>
    </div>
    <div id="result-area"></div>
  `;
  document.getElementById("submit-btn").onclick = () => submitSolution(attempt.id);
}

async function submitSolution(attemptId) {
  const content = document.getElementById("content").value;
  const format = document.getElementById("format").value;
  const resultArea = document.getElementById("result-area");
  try {
    await api(`/attempts/${attemptId}/submissions`, {
      method: "POST",
      body: JSON.stringify({ content, format }),
    });
  } catch (e) {
    resultArea.innerHTML = `<div class="card">${e.message}</div>`;
    return;
  }
  resultArea.innerHTML = `<div class="card spinner">Evaluating your design...</div>`;
  pollAttempt(attemptId, resultArea);
}

function pollAttempt(attemptId, container) {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const attempt = await api(`/attempts/${attemptId}`);
    if (attempt.status === "COMPLETED") {
      clearInterval(pollTimer);
      const fb = await api(`/submissions/${attempt.submission_id}/feedback`);
      container.innerHTML = renderFeedback(fb.feedback);
    } else if (attempt.status === "FAILED") {
      clearInterval(pollTimer);
      container.innerHTML = `
        <div class="card">
          <p class="status FAILED">Evaluation failed: ${attempt.failure_reason || "unknown error"}</p>
          <button class="secondary" id="retry-btn">Retry evaluation</button>
        </div>`;
      document.getElementById("retry-btn").onclick = async () => {
        await api(`/attempts/${attemptId}/retry`, { method: "POST" });
        container.innerHTML = `<div class="card spinner">Retrying evaluation...</div>`;
        pollAttempt(attemptId, container);
      };
    }
  }, 1500);
}

function renderFeedback(fb) {
  const dims = fb.dimension_scores.map(d => `
    <div class="dim-row">
      <div>
        <strong>${d.criterion.replaceAll("_", " ")}</strong><br/>
        <span class="hint">${d.evidence || ""}</span>
        ${d.concern ? `<br/><span class="hint">Concern: ${d.concern}</span>` : ""}
        ${d.suggestion ? `<br/><span class="hint">Suggestion: ${d.suggestion}</span>` : ""}
      </div>
      <div class="score-pill">${d.score}/5</div>
    </div>
  `).join("");
  return `
    <div class="card">
      <h3>Feedback - ${fb.overall_score}/5</h3>
      <p>${fb.summary}</p>
      ${dims}
    </div>
  `;
}

// -- History -----------------------------------------------------------

async function renderHistory() {
  viewHistory.innerHTML = "<p>Loading history...</p>";
  const { attempts } = await api(`/attempts?learner_id=${LEARNER_ID}`);
  if (attempts.length === 0) {
    viewHistory.innerHTML = "<p>No attempts yet - start one from the Practice tab.</p>";
    return;
  }
  const problems = {};
  for (const a of attempts) {
    if (!problems[a.problem_id]) problems[a.problem_id] = await api(`/problems/${a.problem_id}`);
  }
  viewHistory.innerHTML = attempts.map(a => `
    <div class="card">
      <h3>${problems[a.problem_id].title}</h3>
      <p class="status ${a.status}">${a.status}</p>
      <p class="hint">Started ${new Date(a.created_at * 1000).toLocaleString()}</p>
      <div id="hist-fb-${a.id}"></div>
    </div>
  `).join("");
  for (const a of attempts) {
    if (a.status === "COMPLETED" && a.submission_id) {
      const fb = await api(`/submissions/${a.submission_id}/feedback`);
      if (fb.ready) {
        document.getElementById(`hist-fb-${a.id}`).innerHTML = renderFeedback(fb.feedback);
      }
    }
  }
}

// -- init ----------------------------------------------------------------

renderProblemList();
