/* global marked */
(() => {
  const state = {
    projects: [],
    scanRoots: [],
    projectId: null,
    tasks: [],
    progress: null,
    taskDir: null,
    detail: null,
    review: null,
    tab: "overview",
    specTree: null,
    specFile: null,
    specPath: null,
    pickerPath: null,
    pickerData: null,
    lastScanRoot: null,
    scanning: false,
  };

  const $ = (id) => document.getElementById(id);

  async function api(path, options = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    let body = null;
    const text = await res.text();
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      body = { error: text || res.statusText };
    }
    if (!res.ok) {
      const err =
        (body && (body.error || (body.detail && body.detail.error) || body.detail)) ||
        res.statusText;
      const message = typeof err === "string" ? err : JSON.stringify(err);
      throw new Error(message);
    }
    return body;
  }

  function showProjectError(msg) {
    const el = $("project-error");
    if (!msg) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.hidden = false;
    el.textContent = msg;
  }

  function showPickerError(msg) {
    const el = $("picker-error");
    if (!msg) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.hidden = false;
    el.textContent = msg;
  }

  function readinessDot(level) {
    const cls = level || "ok";
    return `<span class="dot ${cls}" title="${cls}"></span>`;
  }

  function statusBadge(status) {
    const s = status || "unknown";
    return `<span class="badge ${s}">${s}</span>`;
  }

  function judgmentBadge(review) {
    if (!review || !review.judgment) return "";
    const j = review.judgment;
    const labels = {
      ready_to_archive: "可結案",
      needs_verification: "待手測",
      in_progress: "進行中",
      planning: "規劃中",
      insufficient_evidence: "證據不足",
    };
    return `<span class="badge judgment ${j}" title="${escapeAttr(j)}">${labels[j] || j}</span>`;
  }

  function activeScanRoot() {
    if (state.lastScanRoot) {
      return state.scanRoots.find((s) => s.path === state.lastScanRoot) || null;
    }
    if (state.scanRoots.length) return state.scanRoots[state.scanRoots.length - 1];
    return null;
  }

  function renderWorkspaceInfo() {
    const el = $("workspace-info");
    const sr = activeScanRoot();
    if (!sr) {
      el.hidden = true;
      el.innerHTML = "";
      return;
    }
    el.hidden = false;
    el.innerHTML = `
      <div class="ws-label">工作區</div>
      <div class="ws-path" title="${escapeAttr(sr.path)}">${escapeHtml(sr.path)}</div>
      <div class="ws-meta">${state.projects.length} 個 Trellis 專案${
        sr.lastScanAt ? ` · 掃描於 ${escapeHtml(sr.lastScanAt)}` : ""
      }</div>`;
  }

  function renderProjects() {
    renderWorkspaceInfo();
    const ul = $("project-list");
    ul.innerHTML = "";
    if (!state.projects.length) {
      ul.innerHTML = `<li class="empty" style="cursor:default">尚未掃描專案<br/><span class="muted">點「選擇資料夾」開始</span></li>`;
      return;
    }
    for (const p of state.projects) {
      const li = document.createElement("li");
      if (p.id === state.projectId) li.classList.add("active");
      const rel = p.relPath && p.relPath !== "." ? p.relPath : "";
      li.innerHTML = `
        <div class="title">${escapeHtml(p.label)}</div>
        <div class="meta">${escapeHtml(rel || p.path)}</div>
        <div class="project-actions">
          <button
            type="button"
            class="ghost danger btn-remove"
            data-id="${escapeAttr(p.id)}"
            title="僅從清單移除，不刪除磁碟檔案"
          >移除</button>
        </div>`;
      li.addEventListener("click", (e) => {
        if (e.target.closest(".btn-remove")) return;
        selectProject(p.id);
      });
      li.querySelector(".btn-remove").addEventListener("click", async (e) => {
        e.stopPropagation();
        await removeProjectFromList(p.id);
      });
      ul.appendChild(li);
    }
  }

  async function removeProjectFromList(id) {
    showProjectError("");
    try {
      await api(`/api/projects/${encodeURIComponent(id)}`, { method: "DELETE" });
      if (state.projectId === id) {
        state.projectId = null;
        state.tasks = [];
        state.progress = null;
        state.detail = null;
        state.taskDir = null;
      }
      await loadProjects();
      if (!state.projectId && state.projects.length) {
        await selectProject(state.projects[0].id);
      } else {
        renderTasks();
        renderDetail();
      }
    } catch (e) {
      showProjectError(e.message);
    }
  }

  async function clearProjectList() {
    if (!state.projects.length) return;
    if (!confirm("清空介面清單？\n（不會刪除磁碟上任何檔案；重新掃描時已移除的項目預設仍會隱藏）")) {
      return;
    }
    showProjectError("");
    try {
      await api("/api/projects", { method: "DELETE" });
      state.projectId = null;
      state.tasks = [];
      state.progress = null;
      state.detail = null;
      state.taskDir = null;
      await loadProjects();
      renderTasks();
      renderDetail();
    } catch (e) {
      showProjectError(e.message);
    }
  }

  async function unhideAndRescan() {
    showProjectError("");
    try {
      await api("/api/projects/unhide", { method: "POST", body: "{}" });
      const sr = activeScanRoot();
      if (sr) {
        await scanFolder(sr.path);
      } else {
        showProjectError("已清除隱藏記錄。請再「選擇資料夾」掃描一次。");
      }
    } catch (e) {
      showProjectError(e.message);
    }
  }

  function renderProgress() {
    const el = $("progress-panel");
    if (!state.progress || !state.projectId) {
      el.hidden = true;
      el.innerHTML = "";
      return;
    }
    const p = state.progress;
    const total = p.total || 0;
    const st = p.byStatus || {};
    const planning = st.planning || 0;
    const inProg = st.in_progress || 0;
    const completed = st.completed || 0;
    const other = Math.max(0, total - planning - inProg - completed);
    const pct = (n) => (total ? Math.round((100 * n) / total) : 0);

    el.hidden = false;
    el.innerHTML = `
      <div class="progress-summary">
        <strong>${total}</strong> active tasks
      </div>
      <div class="progress-bar" title="planning / in_progress / completed / other">
        <span class="seg planning" style="width:${pct(planning)}%"></span>
        <span class="seg in_progress" style="width:${pct(inProg)}%"></span>
        <span class="seg completed" style="width:${pct(completed)}%"></span>
        <span class="seg other" style="width:${pct(other)}%"></span>
      </div>
      <div class="progress-legend">
        <span><i class="swatch planning"></i>planning ${planning}</span>
        <span><i class="swatch in_progress"></i>in_progress ${inProg}</span>
        <span><i class="swatch completed"></i>completed ${completed}</span>
      </div>
      <div class="progress-artifacts muted">
        產物：PRD ${p.artifacts?.prd ?? 0} · Design ${p.artifacts?.design ?? 0} · Implement ${p.artifacts?.implement ?? 0}
      </div>`;
  }

  function renderTasks() {
    const empty = $("tasks-empty");
    const ul = $("task-list");
    renderProgress();
    if (!state.projectId) {
      empty.hidden = false;
      empty.textContent = "選擇左側專案以查看 tasks 與進度";
      ul.hidden = true;
      return;
    }
    if (!state.tasks.length) {
      empty.hidden = false;
      empty.textContent = "此專案沒有 active tasks";
      ul.hidden = true;
      return;
    }
    empty.hidden = true;
    ul.hidden = false;
    ul.innerHTML = "";
    for (const t of state.tasks) {
      const li = document.createElement("li");
      if (t.dirName === state.taskDir) li.classList.add("active");
      const level = (t.readiness && t.readiness.level) || "ok";
      const arts = t.artifacts || {};
      const artBits = [
        arts.prd ? "P" : "·",
        arts.design ? "D" : "·",
        arts.implement ? "I" : "·",
      ].join("");
      const score =
        t.review && typeof t.review.score === "number"
          ? Math.round(t.review.score * 100) + "%"
          : "";
      li.innerHTML = `
        <div class="title">${escapeHtml(t.title || t.dirName)}</div>
        <div class="meta">
          ${readinessDot(level)}
          ${judgmentBadge(t.review)}
          ${statusBadge(t.status)}
          ${t.priority ? `<span class="badge">${escapeHtml(t.priority)}</span>` : ""}
          ${score ? `<span class="muted">${score}</span>` : ""}
          <span class="art-bits" title="PRD / Design / Implement">${artBits}</span>
        </div>`;
      li.addEventListener("click", () => selectTask(t.dirName));
      ul.appendChild(li);
    }
  }

  function renderDetail() {
    const empty = $("detail-empty");
    const detail = $("detail");
    if (!state.detail) {
      empty.hidden = false;
      detail.hidden = true;
      return;
    }
    empty.hidden = true;
    detail.hidden = false;

    document.querySelectorAll("#tabs button").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.tab === state.tab);
    });

    const content = $("tab-content");
    if (state.tab === "overview") {
      content.innerHTML = renderOverview(state.detail);
    } else if (state.tab === "review") {
      content.innerHTML = renderReview(state.review);
      bindReviewActions();
    } else if (state.tab === "specs") {
      content.innerHTML = `<div class="spec-layout">
        <div class="spec-tree" id="spec-tree-host"></div>
        <div id="spec-file-host"></div>
      </div>`;
      renderSpecTree();
      renderSpecFile();
    } else {
      content.innerHTML = renderDoc(state.detail, state.tab);
    }
  }

  function renderReview(r) {
    if (!r) {
      return `<div class="empty">載入 Review 中或無法取得結果</div>`;
    }
    const pct = Math.round((r.score || 0) * 100);
    const ac = r.evidence?.ac || {};
    const impl = r.evidence?.implement || {};
    const arts = r.evidence?.artifacts || {};
    const flags = (r.flags || [])
      .map((f) => `<span class="flag">${escapeHtml(f)}</span>`)
      .join("");
    const steps = (r.nextSteps || [])
      .map((s, i) => {
        const copyBtn =
          s.actionType === "copy_cli"
            ? `<button type="button" class="primary btn-copy-step" data-text="${escapeAttr(
                s.detail
              )}">複製指令</button>`
            : s.actionType === "open_tab"
              ? `<button type="button" class="ghost btn-open-prd">開 PRD</button>`
              : "";
        return `<div class="review-step">
          <div class="review-step-n">${i + 1}</div>
          <div class="review-step-body">
            <div class="title">${escapeHtml(s.title)}</div>
            <pre class="review-step-detail">${escapeHtml(s.detail)}</pre>
            ${copyBtn}
          </div>
        </div>`;
      })
      .join("");

    const acLine = ac.maintained
      ? `${ac.checked}/${ac.total}（${Math.round((ac.ratio || 0) * 100)}%）`
      : "AC 未維護（無 checkbox）";
    const implLine = !arts.implement
      ? "無 implement.md"
      : impl.maintained
        ? `${impl.checked}/${impl.total}（${Math.round((impl.ratio || 0) * 100)}%）`
        : "有檔但無 checkbox";

    return `
      <div class="review-disclaimer">
        此為<strong>文件證據</strong>判斷（${escapeHtml(r.rulesVersion || "")}），不替代手測；
        <strong>不會</strong>修改 Trellis 狀態或刪除檔案。
      </div>
      <div class="review-hero judgment-bg ${escapeAttr(r.judgment)}">
        <div class="review-score">${pct}<span class="unit">%</span></div>
        <div>
          <div class="review-judgment">${judgmentBadge(r)}</div>
          <p class="review-summary">${escapeHtml(r.summary || "")}</p>
        </div>
      </div>
      <div class="overview-grid">
        <div class="card"><div class="label">PRD checklist</div><div class="value">${escapeHtml(acLine)}</div></div>
        <div class="card"><div class="label">Implement checklist</div><div class="value">${escapeHtml(implLine)}</div></div>
        <div class="card"><div class="label">Artifacts</div><div class="value">P ${arts.prd ? "✓" : "—"} · D ${arts.design ? "✓" : "—"} · I ${arts.implement ? "✓" : "—"}</div></div>
        <div class="card"><div class="label">Status</div><div class="value">${escapeHtml(r.status || "—")}</div></div>
      </div>
      <div class="card" style="margin-top:12px">
        <div class="label">Flags</div>
        <div class="flags">${flags || '<span class="flag">none</span>'}</div>
      </div>
      <h3 style="margin:20px 0 10px">建議下一步</h3>
      <div class="review-steps">${steps}</div>
      <div class="card" style="margin-top:16px">
        <div class="label">Archive CLI（在被檢視專案根目錄執行）</div>
        <pre class="review-step-detail" id="archive-cmd-text">${escapeHtml(r.archiveCommand || "")}</pre>
        <button type="button" class="primary" id="btn-copy-archive">複製 archive 指令</button>
      </div>
    `;
  }

  function bindReviewActions() {
    const copyArchive = $("btn-copy-archive");
    if (copyArchive && state.review?.archiveCommand) {
      copyArchive.addEventListener("click", () => {
        copyText(state.review.archiveCommand);
      });
    }
    document.querySelectorAll(".btn-copy-step").forEach((btn) => {
      btn.addEventListener("click", () => copyText(btn.dataset.text || ""));
    });
    document.querySelectorAll(".btn-open-prd").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.tab = "prd";
        renderDetail();
      });
    });
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
  }

  function renderOverview(d) {
    const r = d.readiness || { level: "ok", flags: [] };
    const arts = d.artifacts || {};
    const flags = (r.flags || [])
      .map((f) => `<span class="flag">${escapeHtml(f)}</span>`)
      .join("");
    const fields = [
      ["Title", d.title],
      ["Status", d.status],
      ["Priority", d.priority],
      ["Assignee", d.assignee],
      ["Package", d.package],
      ["Scope", d.scope],
      ["Dir", d.dirName],
      ["Readiness", r.level],
    ];
    const cards = fields
      .map(
        ([label, value]) => `
      <div class="card">
        <div class="label">${label}</div>
        <div class="value">${escapeHtml(value ?? "—")}</div>
      </div>`
      )
      .join("");

    const artList = ["prd", "design", "implement", "implementJsonl", "checkJsonl"]
      .map((k) => {
        const ok = arts[k];
        return `<span class="flag">${k}: ${ok ? "✓" : "—"}</span>`;
      })
      .join("");

    return `
      <h2 style="margin-top:0">${escapeHtml(d.title || d.dirName)}</h2>
      <p style="color:var(--muted)">${escapeHtml(d.description || "")}</p>
      <div class="overview-grid">${cards}</div>
      <div class="card">
        <div class="label">Artifacts</div>
        <div class="flags">${artList}</div>
      </div>
      <div class="card" style="margin-top:12px">
        <div class="label">Readiness flags</div>
        <div class="flags">${flags || '<span class="flag">none</span>'}</div>
      </div>
      ${d.error ? `<div class="error-banner" style="margin-top:12px">${escapeHtml(d.error)}</div>` : ""}
      ${d.notes ? `<div class="card" style="margin-top:12px"><div class="label">Notes</div><div class="value">${escapeHtml(d.notes)}</div></div>` : ""}
    `;
  }

  function renderDoc(d, key) {
    const doc = (d.documents && d.documents[key]) || null;
    if (!doc || doc.missing) {
      return `<div class="empty">${key}.md 不存在</div>`;
    }
    const note = doc.truncated
      ? `<div class="truncated-note">內容已截斷（超過伺服器讀取上限）</div>`
      : "";
    const html =
      typeof marked !== "undefined"
        ? marked.parse(doc.content || "")
        : `<pre class="md">${escapeHtml(doc.content || "")}</pre>`;
    return `${note}<div class="markdown-body">${html}</div>`;
  }

  function renderSpecTree() {
    const host = $("spec-tree-host");
    if (!host) return;
    if (!state.specTree) {
      host.innerHTML = `<div class="empty">無 .trellis/spec</div>`;
      return;
    }
    host.innerHTML = `<ul>${specNodeHtml(state.specTree)}</ul>`;
    host.querySelectorAll(".node.file").forEach((el) => {
      el.addEventListener("click", () => loadSpecFile(el.dataset.path));
    });
  }

  function specNodeHtml(node) {
    if (!node) return "";
    if (node.type === "file") {
      const active = state.specPath === node.relPath ? "active" : "";
      return `<li><span class="node file ${active}" data-path="${escapeAttr(
        node.relPath
      )}">${escapeHtml(node.name)}</span></li>`;
    }
    const kids = (node.children || []).map(specNodeHtml).join("");
    const label = node.relPath === "" ? "spec" : escapeHtml(node.name);
    return `<li><span class="dir-label">📁 ${label}</span><ul>${kids}</ul></li>`;
  }

  function renderSpecFile() {
    const host = $("spec-file-host");
    if (!host) return;
    if (!state.specFile) {
      host.innerHTML = `<div class="empty">選擇一個 spec 檔案</div>`;
      return;
    }
    const note = state.specFile.truncated
      ? `<div class="truncated-note">內容已截斷</div>`
      : "";
    const html =
      typeof marked !== "undefined"
        ? marked.parse(state.specFile.content || "")
        : `<pre class="md">${escapeHtml(state.specFile.content || "")}</pre>`;
    host.innerHTML = `${note}<div class="meta" style="margin-bottom:8px;color:var(--muted)">${escapeHtml(
      state.specFile.relPath
    )}</div><div class="markdown-body">${html}</div>`;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  async function loadProjects() {
    const data = await api("/api/projects");
    state.projects = data.projects || [];
    state.scanRoots = data.scanRoots || [];
    if (state.scanRoots.length && !state.lastScanRoot) {
      state.lastScanRoot = state.scanRoots[state.scanRoots.length - 1].path;
    }
    renderProjects();
  }

  async function openPicker() {
    $("picker-modal").hidden = false;
    showPickerError("");
    try {
      await loadPicker(state.pickerPath || state.lastScanRoot || null);
    } catch (e) {
      showPickerError(e.message);
    }
  }

  function closePicker() {
    $("picker-modal").hidden = true;
  }

  async function loadPicker(path) {
    const q = path ? `?path=${encodeURIComponent(path)}` : "";
    const data = await api(`/api/browse${q}`);
    state.pickerData = data;
    state.pickerPath = data.path;
    $("picker-path").value = data.path;
    $("btn-picker-up").disabled = !data.parent;
    $("picker-trellis-hint").textContent = data.hasTrellis
      ? "此資料夾本身含 .trellis（也會被列入）"
      : "此資料夾本身沒有 .trellis，會掃描子目錄";

    const ul = $("picker-entries");
    ul.innerHTML = "";
    if (!data.entries.length) {
      ul.innerHTML = `<li class="empty">沒有可進入的子資料夾</li>`;
      return;
    }
    for (const ent of data.entries) {
      const li = document.createElement("li");
      li.innerHTML = `
        <span class="picker-name">📁 ${escapeHtml(ent.name)}</span>
        ${ent.hasTrellis ? '<span class="badge in_progress">.trellis</span>' : ""}`;
      li.addEventListener("click", () => loadPicker(ent.path).catch((e) => showPickerError(e.message)));
      li.addEventListener("dblclick", () => loadPicker(ent.path).catch((e) => showPickerError(e.message)));
      ul.appendChild(li);
    }
  }

  async function scanFolder(path) {
    if (state.scanning) return;
    state.scanning = true;
    showProjectError("");
    $("btn-picker-select").disabled = true;
    $("btn-pick-folder").disabled = true;
    try {
      const result = await api("/api/scan", {
        method: "POST",
        body: JSON.stringify({ path, replace: true, maxDepth: 6 }),
      });
      state.lastScanRoot = result.scanRoot?.path || path;
      closePicker();
      await loadProjects();
      // auto-select first project
      if (state.projects.length) {
        await selectProject(state.projects[0].id);
      } else {
        state.projectId = null;
        state.tasks = [];
        state.progress = null;
        state.detail = null;
        renderTasks();
        renderDetail();
      }
    } catch (e) {
      showPickerError(e.message);
      showProjectError(e.message);
    } finally {
      state.scanning = false;
      $("btn-picker-select").disabled = false;
      $("btn-pick-folder").disabled = false;
    }
  }

  async function rescan() {
    const sr = activeScanRoot();
    if (!sr) {
      showProjectError("尚無工作區，請先選擇資料夾");
      return;
    }
    await scanFolder(sr.path);
  }

  async function selectProject(id) {
    state.projectId = id;
    state.taskDir = null;
    state.detail = null;
    state.review = null;
    state.specTree = null;
    state.specFile = null;
    state.specPath = null;
    renderProjects();
    try {
      const data = await api(`/api/projects/${id}/tasks`);
      state.tasks = data.tasks || [];
      state.progress = data.progress || null;
    } catch (e) {
      state.tasks = [];
      state.progress = null;
      showProjectError(e.message);
    }
    renderTasks();
    renderDetail();
  }

  async function selectTask(dirName) {
    state.taskDir = dirName;
    state.tab = "review";
    state.specFile = null;
    state.specPath = null;
    state.review = null;
    renderTasks();
    try {
      state.detail = await api(
        `/api/projects/${state.projectId}/tasks/${encodeURIComponent(dirName)}`
      );
      state.review = await api(
        `/api/projects/${state.projectId}/tasks/${encodeURIComponent(dirName)}/review`
      );
      const tree = await api(`/api/projects/${state.projectId}/specs/tree`);
      state.specTree = tree.tree;
    } catch (e) {
      state.detail = null;
      state.review = null;
      alert(e.message);
    }
    renderDetail();
  }

  async function loadSpecFile(relPath) {
    state.specPath = relPath;
    try {
      state.specFile = await api(
        `/api/projects/${state.projectId}/specs/file?path=${encodeURIComponent(relPath)}`
      );
    } catch (e) {
      state.specFile = { relPath, content: `Error: ${e.message}`, truncated: false };
    }
    renderSpecTree();
    renderSpecFile();
  }

  function bind() {
    $("btn-pick-folder").addEventListener("click", openPicker);
    $("btn-rescan").addEventListener("click", () => rescan().catch((e) => showProjectError(e.message)));
    $("btn-clear-list").addEventListener("click", () => clearProjectList());
    $("btn-unhide").addEventListener("click", () => unhideAndRescan());
    $("btn-close-picker").addEventListener("click", closePicker);
    $("btn-picker-cancel").addEventListener("click", closePicker);
    $("picker-modal").addEventListener("click", (e) => {
      if (e.target.dataset.close) closePicker();
    });
    $("btn-picker-up").addEventListener("click", () => {
      if (state.pickerData?.parent) {
        loadPicker(state.pickerData.parent).catch((e) => showPickerError(e.message));
      }
    });
    $("btn-picker-go").addEventListener("click", () => {
      loadPicker($("picker-path").value.trim()).catch((e) => showPickerError(e.message));
    });
    $("picker-path").addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        loadPicker($("picker-path").value.trim()).catch((err) => showPickerError(err.message));
      }
    });
    $("btn-picker-select").addEventListener("click", () => {
      const path = $("picker-path").value.trim() || state.pickerPath;
      if (path) scanFolder(path);
    });
    $("tabs").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-tab]");
      if (!btn) return;
      state.tab = btn.dataset.tab;
      renderDetail();
    });
  }

  bind();
  loadProjects()
    .then(() => {
      if (state.projects.length) {
        return selectProject(state.projects[0].id);
      }
    })
    .catch((e) => showProjectError(e.message));
})();
