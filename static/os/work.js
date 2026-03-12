(function () {
  "use strict";

  if (window.__HT_WORK_OS_V2__) return;
  window.__HT_WORK_OS_V2__ = true;

  if (document.body?.dataset?.page !== "work-os") return;

  const CFG = window.HT_OS_WORK || {};

  const $ = (id) => document.getElementById(id);
  const qs = (sel, root = document) => root.querySelector(sel);
  const qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const STATE = {
    items: [],
    selectedTaskId: null,
    dragTaskId: null,
    filters: {
      keyword: "",
      status: "",
      priority: "",
      assignee: "",
      shop: "",
    },
  };
    const RESOURCE_STATE = {
      docs: [],
      sheets: [],
    };

    function getSelectedTaskId() {
      return STATE.selectedTaskId ? String(STATE.selectedTaskId) : "";
    }

    function renderTaskDocs(items) {
      const box = $("taskDocsList");
      if (!box) return;

      const arr = Array.isArray(items) ? items : [];
      RESOURCE_STATE.docs = arr;

      if (!arr.length) {
        box.innerHTML = `<div class="resource-empty">Chưa có document</div>`;
        return;
      }

      box.innerHTML = arr.map((x) => `
        <div class="resource-item">
          <div class="resource-item-title">${escapeHtml(x.title || ("Doc #" + x.id))}</div>
          <div class="resource-item-meta">
            Type: ${escapeHtml(x.doc_type || "-")}
          </div>
          <div class="resource-item-actions">
            <a class="btn mini" href="/os/docs/${escapeHtml(x.id)}" target="_blank" rel="noopener">Mở doc</a>
          </div>
        </div>
      `).join("");
    }

    function renderTaskSheets(items) {
      const box = $("taskSheetsList");
      if (!box) return;

      const arr = Array.isArray(items) ? items : [];
      RESOURCE_STATE.sheets = arr;

      if (!arr.length) {
        box.innerHTML = `<div class="resource-empty">Chưa có sheet</div>`;
        return;
      }

      box.innerHTML = arr.map((x) => `
        <div class="resource-item">
          <div class="resource-item-title">${escapeHtml(x.name || ("Sheet #" + x.id))}</div>
          <div class="resource-item-meta">
            Module: ${escapeHtml(x.module_code || "-")}
          </div>
          <div class="resource-item-actions">
            <a class="btn mini" href="/os/sheets/${escapeHtml(x.id)}" target="_blank" rel="noopener">Mở sheet</a>
            <a class="btn mini" href="/api/v1/sheets/${escapeHtml(x.id)}/export.xlsx" target="_blank" rel="noopener">Export Excel</a>
          </div>
        </div>
      `).join("");
    }

  function getCookie(name) {
    const m = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
    return m ? decodeURIComponent(m[2]) : null;
  }

  async function http(url, opts = {}) {
    const headers = Object.assign({}, opts.headers || {});
    const tenantId =
      String(window.HT_TENANT_ID || "").trim() ||
      String(localStorage.getItem("ht_tenant_id") || "").trim();

    if (tenantId) headers["X-Tenant-Id"] = tenantId;

    const method = String(opts.method || "GET").toUpperCase();
    const csrf = getCookie("csrftoken");
    if (csrf && method !== "GET") headers["X-CSRFToken"] = csrf;

    let res;
    try {
      res = await fetch(url, {
        credentials: "include",
        cache: "no-store",
        ...opts,
        headers,
      });
    } catch (err) {
      throw new Error(`Fetch fail: ${url} :: ${err.message}`);
    }

    const ct = res.headers.get("content-type") || "";
    const data = ct.includes("application/json")
      ? await res.json()
      : await res.text();

    if (!res.ok) {
      const msg =
        (data && (data.message || data.detail || data.error)) ||
        (typeof data === "string" ? data : JSON.stringify(data));
      throw new Error(`${res.status} ${res.statusText} :: ${msg || "HTTP error"}`);
    }

    return data;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function fmtTime(iso) {
    if (!iso) return "-";
    try {
      return new Date(iso).toLocaleString("vi-VN");
    } catch (e) {
      return String(iso);
    }
  }

  function toDatetimeLocal(iso) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return "";
      const pad = (n) => String(n).padStart(2, "0");
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    } catch (e) {
      return "";
    }
  }

  function normalizeTaskItem(raw) {
    const x = raw || {};
    return {
      ...x,
      id: x.id,
      title: x.title || `Task #${x.id || ""}`,
      description: x.description || "",
      status: String(x.status || "todo").toLowerCase(),
      priority: Number(x.priority || 2),
      assignee_id: x.assignee_id || "",
      assignee_name: x.assignee_name || "",
      assignee_email: x.assignee_email || "",
      company_id: x.company_id || "",
      company_name: x.company_name || "",
      shop_id: x.shop_id || "",
      shop_name: x.shop_name || "",
      project_id: x.project_id || "",
      project_name: x.project_name || "",
      due_at: x.due_at || null,
      created_at: x.created_at || null,
      updated_at: x.updated_at || null,
    };
  }

  function getCurrentShopId() {
    return (
      String(window.HT_CURRENT_SHOP_ID || "").trim() ||
      String(localStorage.getItem("ht_shop_id") || "").trim() ||
      ""
    );
  }

  function getCurrentProjectId() {
    return (
      String(window.HT_CURRENT_PROJECT_ID || "").trim() ||
      String(localStorage.getItem("ht_project_id") || "").trim() ||
      ""
    );
  }

  function getKnownShops() {
    const map = new Map();

    (STATE.items || []).forEach((x) => {
      const id = String(x.shop_id || "").trim();
      if (!id) return;

      map.set(id, {
        id,
        name: String(x.shop_name || `Shop #${id}`),
      });
    });

    const currentShopId = getCurrentShopId();
    if (currentShopId && !map.has(currentShopId)) {
      map.set(currentShopId, {
        id: currentShopId,
        name: `Shop #${currentShopId}`,
      });
    }

    return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name));
  }

  function getKnownProjectsByShop(shopId = "") {
    const sid = String(shopId || "").trim();
    const map = new Map();

    (STATE.items || []).forEach((x) => {
      const pid = String(x.project_id || "").trim();
      if (!pid) return;
      if (sid && String(x.shop_id || "").trim() !== sid) return;

      map.set(pid, {
        id: pid,
        name: String(x.project_name || `Dự án #${pid}`),
        shop_id: String(x.shop_id || "").trim(),
      });
    });

    const currentProjectId = getCurrentProjectId();
    if (currentProjectId && !map.has(currentProjectId)) {
      map.set(currentProjectId, {
        id: currentProjectId,
        name: `Dự án #${currentProjectId}`,
        shop_id: sid,
      });
    }

    return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name));
  }

  function renderCreateTaskShopOptions() {
    const el = $("createTaskShopId");
    if (!el) return;

    const shops = getKnownShops();
    const currentShopId = getCurrentShopId();

    if (el.tagName === "SELECT") {
      let html = `<option value="">-- Chọn shop --</option>`;
      shops.forEach((shop) => {
        const selected = String(shop.id) === String(currentShopId) ? "selected" : "";
        html += `<option value="${escapeHtml(shop.id)}" ${selected}>${escapeHtml(shop.name)}</option>`;
      });
      el.innerHTML = html;

      if (currentShopId) {
        el.value = currentShopId;
      } else if (shops.length === 1) {
        el.value = String(shops[0].id);
      }
    } else {
      el.value = currentShopId;
    }
  }

  function renderCreateTaskProjectOptions() {
    const selectEl = $("createTaskProjectSelect");
    const inputEl = $("createTaskProjectId");

    if (!selectEl) {
      if (inputEl) inputEl.value = getCurrentProjectId();
      return;
    }

    const shopId =
      String($("createTaskShopId")?.value || "").trim() ||
      getCurrentShopId();

    const projects = getKnownProjectsByShop(shopId);
    const currentProjectId =
      String(inputEl?.value || "").trim() ||
      getCurrentProjectId();

    let html = `<option value="">-- Chọn dự án --</option>`;
    projects.forEach((p) => {
      const selected = String(p.id) === String(currentProjectId) ? "selected" : "";
      html += `<option value="${escapeHtml(p.id)}" ${selected}>${escapeHtml(p.name)}</option>`;
    });

    selectEl.innerHTML = html;

    if (currentProjectId && projects.find((x) => String(x.id) === String(currentProjectId))) {
      selectEl.value = currentProjectId;
    } else if (!currentProjectId && projects.length === 1) {
      selectEl.value = String(projects[0].id);
    } else {
      selectEl.value = "";
    }

    if (inputEl) {
      inputEl.value = String(selectEl.value || "").trim();
    }
  }

  function hydrateCreateTaskContext() {
    renderCreateTaskShopOptions();
    renderCreateTaskProjectOptions();

    const shopId =
      String($("createTaskShopId")?.value || "").trim() ||
      getCurrentShopId();

    const projectId =
      String($("createTaskProjectId")?.value || "").trim() ||
      getCurrentProjectId();

    const hint = $("createTaskContextLine");
    if (hint) {
      const parts = [];
      if (shopId) parts.push(`Shop #${shopId}`);
      if (projectId) parts.push(`Project #${projectId}`);
      hint.textContent = parts.length
        ? `Ngữ cảnh hiện tại: ${parts.join(" • ")}`
        : "Tạo task theo ngữ cảnh hiện tại.";
    }
  }

  function taskMetaText(t) {
    const assigneeText =
      t.assignee_name
        ? `${t.assignee_name}${t.assignee_email ? " • " + t.assignee_email : ""}`
        : (t.assignee_email || (t.assignee_id ? `User #${t.assignee_id}` : "Chưa giao"));

    const shopText = t.shop_name || (t.shop_id ? `#${t.shop_id}` : "-");
    const projectText = t.project_name || (t.project_id ? `#${t.project_id}` : "-");

    const priorityMap = {
      1: "Thấp",
      2: "Vừa",
      3: "Cao",
      4: "Gấp",
    };

    return {
      assigneeText,
      shopText,
      projectText,
      priorityText: priorityMap[t.priority] || String(t.priority || "-"),
    };
  }

  function findTaskById(taskId) {
    return STATE.items.find((x) => String(x.id) === String(taskId)) || null;
  }

  function patchTaskLocal(taskId, patch = {}) {
    const id = String(taskId);
    let found = false;

    STATE.items = STATE.items.map((x) => {
      if (String(x.id) === id) {
        found = true;
        return normalizeTaskItem({ ...x, ...patch });
      }
      return x;
    });

    if (!found) {
      STATE.items.unshift(normalizeTaskItem({ id: taskId, ...patch }));
    }
  }

  function sortStateItems() {
    const orderMap = {
      todo: 1,
      doing: 2,
      blocked: 3,
      done: 4,
      cancelled: 5,
    };

    STATE.items = [...STATE.items].sort((a, b) => {
      const sa = orderMap[String(a.status || "todo")] || 99;
      const sb = orderMap[String(b.status || "todo")] || 99;
      if (sa !== sb) return sa - sb;

      const ra = String(a.rank || "");
      const rb = String(b.rank || "");
      if (ra && rb && ra !== rb) return ra.localeCompare(rb);

      return Number(a.id || 0) - Number(b.id || 0);
    });
  }

  function calcDropPosition(col, draggedId) {
    const cards = qsa(".work-card", col).filter((x) => String(x.dataset.id) !== String(draggedId));
    if (!cards.length) return 1;

    const y = window.__HT_WORK_DROP_Y__ || 0;
    let pos = cards.length + 1;

    for (let i = 0; i < cards.length; i++) {
      const rect = cards[i].getBoundingClientRect();
      const mid = rect.top + rect.height / 2;
      if (y < mid) {
        pos = i + 1;
        break;
      }
    }

    return pos;
  }

  function matchFilter(task) {
    const keyword = STATE.filters.keyword.trim().toLowerCase();
    const status = STATE.filters.status.trim().toLowerCase();
    const priority = STATE.filters.priority.trim();
    const assignee = STATE.filters.assignee.trim().toLowerCase();
    const shop = STATE.filters.shop.trim().toLowerCase();

    const hay = [
      task.title,
      task.description,
      task.assignee_name,
      task.assignee_email,
      task.shop_name,
      task.shop_id,
      task.project_name,
      task.project_id,
    ].filter(Boolean).join(" ").toLowerCase();

    const assigneeHay = `${task.assignee_name || ""} ${task.assignee_email || ""} ${task.assignee_id || ""}`.toLowerCase();
    const shopHay = `${task.shop_name || ""} ${task.shop_id || ""}`.toLowerCase();

    if (keyword && !hay.includes(keyword)) return false;
    if (status && String(task.status || "").toLowerCase() !== status) return false;
    if (priority && String(task.priority || "") !== priority) return false;
    if (assignee && !assigneeHay.includes(assignee)) return false;
    if (shop && !shopHay.includes(shop)) return false;

    return true;
  }

  function getFilteredItems() {
    return STATE.items.filter(matchFilter);
  }

  function renderKPIs() {
    const items = getFilteredItems();

    const total = items.length;
    const todo = items.filter((x) => x.status === "todo").length;
    const doing = items.filter((x) => x.status === "doing").length;
    const blocked = items.filter((x) => x.status === "blocked").length;
    const done = items.filter((x) => x.status === "done").length;
    const overdue = items.filter((x) => {
      return x.due_at &&
        new Date(x.due_at).getTime() < Date.now() &&
        !["done", "cancelled"].includes(String(x.status || "").toLowerCase());
    }).length;

    if ($("kpiTotal")) $("kpiTotal").textContent = String(total);
    if ($("kpiTodo")) $("kpiTodo").textContent = String(todo);
    if ($("kpiDoing")) $("kpiDoing").textContent = String(doing);
    if ($("kpiBlocked")) $("kpiBlocked").textContent = String(blocked);
    if ($("kpiDone")) $("kpiDone").textContent = String(done);
    if ($("kpiOverdue")) $("kpiOverdue").textContent = String(overdue);
  }

  function makeCard(t) {
    const meta = taskMetaText(t);

    return `
      <div class="work-card" data-id="${escapeHtml(t.id)}" draggable="true">
        <div class="work-card-title">${escapeHtml(t.title)}</div>

        <div class="work-card-meta">
          <span>#${escapeHtml(t.id)}</span>
          <span>${escapeHtml(meta.priorityText)}</span>
          <span>${escapeHtml(t.status || "-")}</span>
        </div>

        <div class="work-card-meta">
          <span>Assignee: ${escapeHtml(meta.assigneeText)}</span>
        </div>

        <div class="work-card-meta">
          <span>Shop: ${escapeHtml(meta.shopText)}</span>
          <span>Project: ${escapeHtml(meta.projectText)}</span>
        </div>

        ${t.description ? `<div class="work-card-desc">${escapeHtml(t.description)}</div>` : ""}

        <div class="work-card-meta">
          <span>Deadline: ${escapeHtml(fmtTime(t.due_at))}</span>
        </div>

        <div class="work-card-actions">
          <button class="btn mini open-task-btn" data-open-task="${escapeHtml(t.id)}" type="button">Mở</button>
          <button class="btn mini move-next-btn" data-next-task="${escapeHtml(t.id)}" type="button">Next</button>
        </div>
      </div>
    `;
  }

  function renderBoard() {
    const board = $("workBoard");
    if (!board) return;

    const items = getFilteredItems();
    const cols = {
      todo: items.filter((x) => x.status === "todo"),
      doing: items.filter((x) => x.status === "doing"),
      blocked: items.filter((x) => x.status === "blocked"),
      done: items.filter((x) => x.status === "done"),
    };

    function makeCol(key, label) {
      return `
        <div class="work-col">
          <div class="work-col-head">
            <div class="work-col-title">${label}</div>
            <div class="work-col-count">${cols[key].length}</div>
          </div>

          <div class="work-quick-create">
            <input
              class="input quick-create-input"
              data-status="${key}"
              placeholder="Quick add task..."
            />
            <button
              class="btn mini quick-create-btn"
              data-status="${key}"
              type="button"
            >Create</button>
          </div>

          <div class="work-col-list" data-drop-status="${key}">
            ${
              cols[key].length
                ? cols[key].map(makeCard).join("")
                : `<div class="work-empty">No items</div>`
            }
          </div>
        </div>
      `;
    }

    board.innerHTML = `
      ${makeCol("todo", "TODO")}
      ${makeCol("doing", "DOING")}
      ${makeCol("blocked", "BLOCKED")}
      ${makeCol("done", "DONE")}
    `;

    bindBoardDnD();
  }

  function renderAll() {
    sortStateItems();
    renderKPIs();
    renderBoard();
  }

  async function refreshWorkData() {
    if (!CFG.inbox) throw new Error("Thiếu CFG.inbox");

    const tenantId =
      String(window.HT_TENANT_ID || "").trim() ||
      String(localStorage.getItem("ht_tenant_id") || "").trim();

    if (tenantId) localStorage.setItem("ht_tenant_id", tenantId);

    const data = await http(`${CFG.inbox}?page=1&page_size=300`);
    const items = Array.isArray(data?.items) ? data.items : [];

    STATE.items = items.map(normalizeTaskItem);
    renderAll();
  }

  async function createTask(payload) {
    if (!CFG.create) throw new Error("Thiếu CFG.create");
    return http(CFG.create, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  async function moveTask(id, status, toPosition = null) {
    if (!CFG.assignBase) throw new Error("Thiếu CFG.assignBase");

    const oldTask = findTaskById(id);
    if (!oldTask) throw new Error("Không tìm thấy task");

    patchTaskLocal(id, { status, updated_at: new Date().toISOString() });
    renderAll();

    try {
      const resp = await http(`${CFG.assignBase}${id}/move/`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          to_status: status,
          to_position: toPosition,
        }),
      });

      if (resp?.item) {
        patchTaskLocal(id, resp.item);
      } else {
        patchTaskLocal(id, { status });
      }

      renderAll();
    } catch (e) {
      patchTaskLocal(id, oldTask);
      renderAll();
      throw e;
    }
  }

  async function updateTask(taskId, payload) {
    const pure = {};

    if ("title" in payload) pure.title = payload.title;
    if ("description" in payload) pure.description = payload.description;
    if ("priority" in payload) pure.priority = payload.priority;
    if ("due_at" in payload) pure.due_at = payload.due_at;

    if (Object.keys(pure).length) {
      await http(`${CFG.updateBase}${taskId}/update/`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(pure),
      });
    }

    if ("assignee_id" in payload && payload.assignee_id) {
      await http(`${CFG.assignBase}${taskId}/assign/`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ assignee_id: payload.assignee_id }),
      });
    }

    if ("status" in payload && payload.status) {
      await http(`${CFG.assignBase}${taskId}/move/`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ to_status: payload.status }),
      });
    }

    await refreshWorkData();
  }

  async function refreshTaskComments(taskId) {
    if (!taskId || !CFG.commentsBase) return;
    const data = await http(`${CFG.commentsBase}${taskId}/comments/`);
    renderTaskComments(data?.items || []);
  }

    async function refreshTaskDocs(taskId) {
      if (!taskId) return;
      const data = await http(`/api/v1/docs/?linked_target_type=work&linked_target_id=${taskId}`);
      renderTaskDocs(data?.items || []);
    }

    async function refreshTaskSheets(taskId) {
      if (!taskId) return;
      const data = await http(`/api/v1/sheets/?linked_target_type=work&linked_target_id=${taskId}`);
      renderTaskSheets(data?.items || []);
    }

    async function createTaskDocQuick() {
      const taskId = getSelectedTaskId();
      if (!taskId) throw new Error("Chưa chọn task");

      const task = findTaskById(taskId);

      const payload = {
        title: task?.title
          ? `Doc • ${task.title}`
          : `Document task #${taskId}`,
        doc_type: "doc",
        linked_target_type: "work",
        linked_target_id: taskId,
        content_html: `
          <h1>${escapeHtml(task?.title || `Task #${taskId}`)}</h1>
          <p>Tài liệu gắn với task #${taskId}.</p>
          <div class="doc-box"><b>Ghi chú:</b> Có thể dùng cho proposal / note / hướng dẫn triển khai.</div>
        `
      };

      const data = await http(`/api/v1/docs/create/`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });

      await refreshTaskDocs(taskId);

      if (data?.item?.id) {
        window.open(`/os/docs/${data.item.id}/`, "_blank", "noopener");
      }
    }

    async function createTaskSheetQuick() {
      const taskId = getSelectedTaskId();
      if (!taskId) throw new Error("Chưa chọn task");

      const task = findTaskById(taskId);

      const payload = {
        name: task?.title
          ? `Sheet • ${task.title}`
          : `Sheet task #${taskId}`,
        module_code: "work",
        linked_target_type: "work",
        linked_target_id: taskId,
        columns: [
          { name: "Hạng mục", data_type: "text" },
          { name: "Trạng thái", data_type: "select" },
          { name: "Người phụ trách", data_type: "text" },
          { name: "Ghi chú", data_type: "text" }
        ]
      };

      const data = await http(`/api/v1/sheets/create/`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });

      await refreshTaskSheets(taskId);

      if (data?.item?.id) {
        window.open(`/os/sheets/${data.item.id}/`, "_blank", "noopener");
      }
    }
  function openTaskDrawer(task) {
    if (!task) return;

    STATE.selectedTaskId = task.id;

    if ($("taskDrawerSub")) {
      $("taskDrawerSub").textContent = `Task #${task.id} • Shop ${task.shop_id || "-"} • Project ${task.project_id || "-"}`;
    }

    if ($("taskEditTitle")) $("taskEditTitle").value = task.title || "";
    if ($("taskEditDescription")) $("taskEditDescription").value = task.description || "";
    if ($("taskEditStatus")) $("taskEditStatus").value = task.status || "todo";
    if ($("taskEditPriority")) $("taskEditPriority").value = String(task.priority || 2);
    if ($("taskEditDueAt")) $("taskEditDueAt").value = toDatetimeLocal(task.due_at);
    if ($("taskEditAssigneeId")) $("taskEditAssigneeId").value = task.assignee_id || "";
    if ($("taskEditShopId")) $("taskEditShopId").value = task.shop_id || "";
    if ($("taskEditProjectId")) $("taskEditProjectId").value = task.project_id || "";

    const drawer = $("taskDrawer");
    if (drawer) {
      drawer.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";
    }

    renderTaskDocs([]);
    renderTaskSheets([]);

    refreshTaskComments(task.id).catch(console.warn);
    refreshTaskAttachments(task.id).catch(console.warn);
    refreshTaskDocs(task.id).catch(console.warn);
    refreshTaskSheets(task.id).catch(console.warn);
  }

  function closeTaskDrawer() {
    const drawer = $("taskDrawer");
    if (!drawer) return;
    drawer.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    STATE.selectedTaskId = null;
    renderTaskDocs([]);
    renderTaskSheets([]);
  }

  async function saveTaskDrawer() {
    const taskId = STATE.selectedTaskId;
    if (!taskId) throw new Error("Chưa chọn task");

    const payload = {
      title: ($("taskEditTitle")?.value || "").trim(),
      description: ($("taskEditDescription")?.value || "").trim(),
      status: ($("taskEditStatus")?.value || "todo").trim(),
      priority: Number(($("taskEditPriority")?.value || "2").trim() || 2),
      due_at: ($("taskEditDueAt")?.value || "").trim() || null,
      assignee_id: ($("taskEditAssigneeId")?.value || "").trim() || null,
      shop_id: ($("taskEditShopId")?.value || "").trim() || null,
      project_id: ($("taskEditProjectId")?.value || "").trim() || null,
    };

    await updateTask(taskId, payload);

    const fresh = findTaskById(taskId);
    if (fresh) openTaskDrawer(fresh);
  }

  async function moveTaskNextStep(taskId) {
    const task = findTaskById(taskId);
    if (!task) throw new Error("Không tìm thấy task");

    const flow = ["todo", "doing", "blocked", "done"];
    const idx = flow.indexOf(String(task.status || "todo"));
    const next = idx >= 0 && idx < flow.length - 1 ? flow[idx + 1] : "done";

    await moveTask(taskId, next);
  }

  async function submitTaskComment() {
    const taskId = STATE.selectedTaskId;
    if (!taskId) throw new Error("Chưa chọn task");

    const body = ($("taskCommentInput")?.value || "").trim();
    if (!body) {
      alert("Nhập comment đã anh");
      return;
    }

    await http(`${CFG.commentsBase}${taskId}/comments/`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ body }),
    });

    if ($("taskCommentInput")) $("taskCommentInput").value = "";
    await refreshTaskComments(taskId);
  }

  function bindBoardDnD() {
    qsa(".work-card").forEach((card) => {
      card.addEventListener("dragstart", (e) => {
        const id = card.dataset.id;
        STATE.dragTaskId = String(id);
        card.classList.add("dragging");
        e.dataTransfer.setData("text/plain", String(id));
        e.dataTransfer.effectAllowed = "move";
      });

      card.addEventListener("dragend", () => {
        card.classList.remove("dragging");
        STATE.dragTaskId = null;
      });
    });

    qsa(".work-col-list").forEach((col) => {
      col.addEventListener("dragover", (e) => {
        e.preventDefault();
        window.__HT_WORK_DROP_Y__ = e.clientY;
        col.classList.add("drag-over");
      });

      col.addEventListener("dragleave", () => {
        col.classList.remove("drag-over");
      });

      col.addEventListener("drop", async (e) => {
        e.preventDefault();
        col.classList.remove("drag-over");

        const taskId = e.dataTransfer.getData("text/plain") || STATE.dragTaskId;
        const toStatus = col.dataset.dropStatus || "";

        if (!taskId || !toStatus) return;

        try {
          const toPosition = calcDropPosition(col, taskId);
          await moveTask(taskId, toStatus, toPosition);
        } catch (err) {
          alert("Move lỗi: " + err.message);
        }
      });
    });
  }

  function openCreateTaskModal() {
    const m = $("createTaskModal");
    if (!m) return;

    hydrateCreateTaskContext();

    if ($("createTaskPriority")) $("createTaskPriority").value = "2";
    if ($("createTaskError")) $("createTaskError").textContent = "";
    if ($("createTaskOk")) $("createTaskOk").textContent = "";

    m.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";

    setTimeout(() => {
      $("createTaskTitle")?.focus();
    }, 60);
  }

  function closeCreateTaskModal() {
    const m = $("createTaskModal");
    if (!m) return;
    m.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  function resetCreateTaskModal() {
    if ($("createTaskTitle")) $("createTaskTitle").value = "";
    if ($("createTaskDescription")) $("createTaskDescription").value = "";
    if ($("createTaskPriority")) $("createTaskPriority").value = "2";
    if ($("createTaskDueAt")) $("createTaskDueAt").value = "";
    if ($("createTaskAssigneeId")) $("createTaskAssigneeId").value = "";
    if ($("createTaskDepartment")) $("createTaskDepartment").value = "";
    if ($("createTaskBrandName")) $("createTaskBrandName").value = "";
    if ($("createTaskTargetType")) $("createTaskTargetType").value = "";
    if ($("createTaskTargetId")) $("createTaskTargetId").value = "";
    if ($("createTaskError")) $("createTaskError").textContent = "";
    if ($("createTaskOk")) $("createTaskOk").textContent = "";

    hydrateCreateTaskContext();
  }

  async function submitCreateTaskModal() {
    const shopId =
      String($("createTaskShopId")?.value || "").trim() ||
      getCurrentShopId();

    const projectId =
      String($("createTaskProjectId")?.value || "").trim() ||
      getCurrentProjectId();

    const payload = {
      title: ($("createTaskTitle")?.value || "").trim(),
      description: ($("createTaskDescription")?.value || "").trim(),
      shop_id: shopId,
      project_id: projectId,
      priority: Number(($("createTaskPriority")?.value || "2").trim() || 2),
      due_at: ($("createTaskDueAt")?.value || "").trim() || null,
      assignee_id: ($("createTaskAssigneeId")?.value || "").trim() || null,
      department: ($("createTaskDepartment")?.value || "").trim(),
      brand_name: ($("createTaskBrandName")?.value || "").trim(),
      target_type: ($("createTaskTargetType")?.value || "").trim(),
      target_id: ($("createTaskTargetId")?.value || "").trim(),
    };

    if ($("createTaskError")) $("createTaskError").textContent = "";
    if ($("createTaskOk")) $("createTaskOk").textContent = "";

    if (!payload.title) {
      if ($("createTaskError")) $("createTaskError").textContent = "Anh nhập tiêu đề task trước nha.";
      $("createTaskTitle")?.focus();
      return;
    }

    if (!payload.shop_id) {
      if ($("createTaskError")) $("createTaskError").textContent = "Chưa có shop hiện tại để tạo task.";
      $("createTaskShopId")?.focus();
      return;
    }

    if (!payload.description) delete payload.description;
    if (!payload.project_id) delete payload.project_id;
    if (!payload.assignee_id) delete payload.assignee_id;
    if (!payload.due_at) delete payload.due_at;
    if (!payload.department) delete payload.department;
    if (!payload.brand_name) delete payload.brand_name;
    if (!payload.target_type) delete payload.target_type;
    if (!payload.target_id) delete payload.target_id;

    const btn = $("submitCreateTaskBtn");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Đang tạo...";
    }

    try {
      await createTask(payload);
      if ($("createTaskOk")) $("createTaskOk").textContent = "Đã tạo task thành công.";
      closeCreateTaskModal();
      resetCreateTaskModal();
      await refreshWorkData();
    } catch (e) {
      if ($("createTaskError")) $("createTaskError").textContent = "Tạo task lỗi: " + e.message;
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Tạo task";
      }
    }
  }

  function bindEvents() {

    $("btnUploadTaskAttachment")?.addEventListener("click", async () => {
      const btn = $("btnUploadTaskAttachment");
      if (btn) {
        btn.disabled = true;
        btn.textContent = "Đang upload...";
      }

      try {
        await uploadTaskAttachment();
      } catch (e) {
        alert("Upload file lỗi: " + e.message);
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.textContent = "Upload file";
        }
      }
    });

    $("btnCreateTaskDoc")?.addEventListener("click", async () => {
      const btn = $("btnCreateTaskDoc");
      if (btn) {
        btn.disabled = true;
        btn.textContent = "Đang tạo...";
      }

      try {
        await createTaskDocQuick();
      } catch (e) {
        alert("Tạo doc lỗi: " + e.message);
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.textContent = "+ Tạo doc";
        }
      }
    });

    $("btnRefreshTaskDocs")?.addEventListener("click", async () => {
      try {
        await refreshTaskDocs(getSelectedTaskId());
      } catch (e) {
        alert("Load docs lỗi: " + e.message);
      }
    });

    $("btnCreateTaskSheet")?.addEventListener("click", async () => {
      const btn = $("btnCreateTaskSheet");
      if (btn) {
        btn.disabled = true;
        btn.textContent = "Đang tạo...";
      }

      try {
        await createTaskSheetQuick();
      } catch (e) {
        alert("Tạo sheet lỗi: " + e.message);
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.textContent = "+ Tạo sheet";
        }
      }
    });

    $("btnRefreshTaskSheets")?.addEventListener("click", async () => {
      try {
        await refreshTaskSheets(getSelectedTaskId());
      } catch (e) {
        alert("Load sheets lỗi: " + e.message);
      }
    });

    $("btnRefreshWork")?.addEventListener("click", refreshWorkData);

    $("btnApplyFilter")?.addEventListener("click", () => {
      STATE.filters.keyword = $("filterKeyword")?.value || "";
      STATE.filters.status = $("filterStatus")?.value || "";
      STATE.filters.priority = $("filterPriority")?.value || "";
      STATE.filters.assignee = $("filterAssignee")?.value || "";
      STATE.filters.shop = $("filterShop")?.value || "";
      renderAll();
    });

    $("btnResetFilter")?.addEventListener("click", () => {
      STATE.filters.keyword = "";
      STATE.filters.status = "";
      STATE.filters.priority = "";
      STATE.filters.assignee = "";
      STATE.filters.shop = "";

      if ($("filterKeyword")) $("filterKeyword").value = "";
      if ($("filterStatus")) $("filterStatus").value = "";
      if ($("filterPriority")) $("filterPriority").value = "";
      if ($("filterAssignee")) $("filterAssignee").value = "";
      if ($("filterShop")) $("filterShop").value = "";

      renderAll();
    });

    $("createTaskShopId")?.addEventListener("change", (e) => {
      const shopId = String(e.target.value || "").trim();

      if ($("createTaskProjectId")) $("createTaskProjectId").value = "";
      renderCreateTaskProjectOptions();

      if ($("createTaskShopId")) $("createTaskShopId").value = shopId;
      hydrateCreateTaskContext();
    });

    $("createTaskProjectSelect")?.addEventListener("change", (e) => {
      const projectId = String(e.target.value || "").trim();
      if ($("createTaskProjectId")) {
        $("createTaskProjectId").value = projectId;
      }
      hydrateCreateTaskContext();
    });

    $("btnOpenCreateTask")?.addEventListener("click", openCreateTaskModal);
    $("closeCreateTaskBtn")?.addEventListener("click", closeCreateTaskModal);
    $("createTaskBackdrop")?.addEventListener("click", closeCreateTaskModal);
    $("resetCreateTaskBtn")?.addEventListener("click", resetCreateTaskModal);
    $("submitCreateTaskBtn")?.addEventListener("click", submitCreateTaskModal);

    $("btnCloseTaskDrawer")?.addEventListener("click", closeTaskDrawer);
    qsa("[data-drawer-close='1']").forEach((x) => x.addEventListener("click", closeTaskDrawer));

    $("btnSaveTaskDrawer")?.addEventListener("click", async () => {
      try {
        await saveTaskDrawer();
      } catch (e) {
        alert("Lưu task lỗi: " + e.message);
      }
    });

    $("btnMoveNextTaskDrawer")?.addEventListener("click", async () => {
      try {
        await moveTaskNextStep(STATE.selectedTaskId);
        const fresh = findTaskById(STATE.selectedTaskId);
        if (fresh) openTaskDrawer(fresh);
      } catch (e) {
        alert("Move task lỗi: " + e.message);
      }
    });

    $("btnSubmitTaskComment")?.addEventListener("click", async () => {
      try {
        await submitTaskComment();
      } catch (e) {
        alert("Comment lỗi: " + e.message);
      }
    });

    document.addEventListener("click", async (e) => {
      const openBtn = e.target.closest("[data-open-task]");
      if (openBtn) {
        const task = findTaskById(openBtn.dataset.openTask);
        if (task) openTaskDrawer(task);
        return;
      }

      const nextBtn = e.target.closest("[data-next-task]");
      if (nextBtn) {
        try {
          await moveTaskNextStep(nextBtn.dataset.nextTask);
        } catch (err) {
          alert("Move lỗi: " + err.message);
        }
        return;
      }

      const createBtn = e.target.closest(".quick-create-btn");
      if (createBtn) {
        const status = createBtn.dataset.status || "todo";
        const input = qs(`.quick-create-input[data-status="${CSS.escape(status)}"]`);
        const title = (input?.value || "").trim();

        if (!title) {
          alert("Nhập tiêu đề task");
          return;
        }

        try {
          await createTask({
            title,
            status,
            shop_id: getCurrentShopId() || undefined,
            project_id: getCurrentProjectId() || undefined,
          });
          if (input) input.value = "";
          await refreshWorkData();
        } catch (err) {
          alert("Quick create lỗi: " + err.message);
        }
      }
    });

    document.addEventListener("keydown", async (e) => {
      if (e.key === "Escape") {
        closeTaskDrawer();
        closeCreateTaskModal();
      }

      if (e.target?.classList?.contains("quick-create-input") && e.key === "Enter") {
        e.preventDefault();

        const status = e.target.dataset.status || "todo";
        const title = (e.target.value || "").trim();

        if (!title) return;

        try {
          await createTask({
            title,
            status,
            shop_id: getCurrentShopId() || undefined,
            project_id: getCurrentProjectId() || undefined,
          });
          e.target.value = "";
          await refreshWorkData();
        } catch (err) {
          alert("Quick create lỗi: " + err.message);
        }
      }
    });
  }

  async function boot() {
    const tenantId = String(window.HT_TENANT_ID || "").trim();
    if (tenantId) localStorage.setItem("ht_tenant_id", tenantId);

    if (window.HT_CURRENT_SHOP_ID) {
      localStorage.setItem("ht_shop_id", String(window.HT_CURRENT_SHOP_ID).trim());
    }

    if (window.HT_CURRENT_PROJECT_ID) {
      localStorage.setItem("ht_project_id", String(window.HT_CURRENT_PROJECT_ID).trim());
    }

    bindEvents();
    await refreshWorkData();
  }
  async function refreshTaskAttachments(taskId) {
    if (!taskId) return;
    const data = await http(`${CFG.commentsBase}${taskId}/attachments/`);
    renderTaskAttachments(data?.items || []);
  }

  function renderTaskAttachments(items) {
    const box = $("taskAttachmentsList");
    if (!box) return;

    const arr = Array.isArray(items) ? items : [];

    if (!arr.length) {
      box.innerHTML = `<div class="work-empty">Chưa có file</div>`;
      return;
    }

    box.innerHTML = arr.map((x) => {
      const fileName = x.original_name || x.file_name || `File #${x.id}`;
      const contentType = x.content_type || "-";
      const size = Number(x.file_size || 0).toLocaleString("vi-VN");

      return `
        <div class="task-comment-item">
          <div class="t">${escapeHtml(fileName)}</div>
          <div class="time">${escapeHtml(contentType)} • ${escapeHtml(size)} bytes</div>
          <div class="work-card-actions" style="margin-top:8px;">
            <a class="btn mini" href="${escapeHtml(x.viewer_url)}" target="_blank" rel="noopener">Xem trong OS</a>
            <a class="btn mini" href="${escapeHtml(x.preview_url)}" target="_blank" rel="noopener">Preview</a>
            <a class="btn mini" href="${escapeHtml(x.download_url)}" target="_blank" rel="noopener">Tải file</a>
          </div>
        </div>
      `;
    }).join("");
  }

  async function uploadTaskAttachment() {
    const taskId = STATE.selectedTaskId;
    if (!taskId) throw new Error("Chưa chọn task");

    const input = $("taskAttachmentInput");
    const file = input?.files?.[0];

    if (!file) {
      alert("Anh chọn file trước nha");
      return;
    }

    const tenantId =
      String(window.HT_TENANT_ID || "").trim() ||
      String(localStorage.getItem("ht_tenant_id") || "").trim();

    const csrf = getCookie("csrftoken");
    const form = new FormData();
    form.append("file", file);

    const headers = {};
    if (tenantId) headers["X-Tenant-Id"] = tenantId;
    if (csrf) headers["X-CSRFToken"] = csrf;

    const res = await fetch(`${CFG.commentsBase}${taskId}/attachments/upload/`, {
      method: "POST",
      credentials: "include",
      headers,
      body: form,
    });

    const ct = res.headers.get("content-type") || "";
    const data = ct.includes("application/json") ? await res.json() : await res.text();

    if (!res.ok) {
      const msg =
        (data && (data.message || data.detail || data.error)) ||
        (typeof data === "string" ? data : JSON.stringify(data));
      throw new Error(msg || "Upload file lỗi");
    }

    if (input) input.value = "";
    await refreshTaskAttachments(taskId);
  }

  window.htWorkRefresh = refreshWorkData;
  window.htWorkOpenTask = (id) => {
    const task = findTaskById(id);
    if (task) openTaskDrawer(task);
  };
  window.htWorkRefreshTaskDocs = refreshTaskDocs;
  window.htWorkRefreshTaskSheets = refreshTaskSheets;
  window.htWorkCreateTaskDocQuick = createTaskDocQuick;
  window.htWorkCreateTaskSheetQuick = createTaskSheetQuick;
  boot().catch((e) => {
    console.error(e);
    alert("Work OS load lỗi: " + e.message);
  });
})();