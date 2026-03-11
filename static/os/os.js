(function () {
  "use strict";

  if (window.__HT_OS_V12_CLEAN__) return;
  window.__HT_OS_V12_CLEAN__ = true;

  const CFG = window.HT_OS || {};

  const $ = (id) => document.getElementById(id);
  const qs = (sel, root = document) => root.querySelector(sel);
  const qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const STATE = {
    es: null,
    isRefreshing: false,
    sseCooldownAt: 0,
    timelineCursor: null,
    lastTimelineIds: new Set(),
    dragTaskId: null,
    eventsBound: false,

    raw: {
      home: null,
      control: null,
      timeline: null,
      notifications: null,
      work: null,
      active: "home",
    },

    ui: {
      theme: localStorage.getItem("ht_theme") || "dark",
      workView: localStorage.getItem("ht_work_view") || "list",
      boardGroupBy: localStorage.getItem("ht_board_group_by") || "status",
      activeTab: "home",
    },

    scope: {
      scope: localStorage.getItem("ht_scope") || "tenant",
      company_id: localStorage.getItem("ht_company_id") || "",
      shop_id: localStorage.getItem("ht_shop_id") || "",
      project_id: localStorage.getItem("ht_project_id") || "",
      hours: localStorage.getItem("ht_hours") || "24",
    },

    work: {
      selectedTaskId: null,
      open: [],
      todo: [],
      doing: [],
      blocked: [],
      done: [],
      all: [],
      filters: {
        assignee: "",
        keyword: "",
        company: "",
        shop: "",
        status: "",
      },
    },
  };

  function getCookie(name) {
    const m = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
    return m ? decodeURIComponent(m[2]) : null;
  }

  async function sleep(ms){
    return new Promise(r=>setTimeout(r,ms));
  }

  function parseRetrySeconds(message){
    const m = String(message || "").match(/available in\s+(\d+)/i);
    if(m) return Number(m[1]||1);
    return 1;
  }

  async function http(url, opts = {}, retry = 0) {
    const headers = Object.assign({}, opts.headers || {});
    const tenantId =
      String(window.HT_TENANT_ID || "").trim() ||
      String(localStorage.getItem("ht_tenant_id") || "").trim();

    if (tenantId) {
      headers["X-Tenant-Id"] = tenantId;
    }

    const method = (opts.method || "GET").toUpperCase();
    const csrf = getCookie("csrftoken");

    if (csrf && method !== "GET") {
      headers["X-CSRFToken"] = csrf;
    }

    const res = await fetch(url, Object.assign({
      credentials: "include",
      headers,
      cache: "no-store",
    }, opts));

    const ct = res.headers.get("content-type") || "";
    const data = ct.includes("application/json")
      ? await res.json()
      : await res.text();

    if (res.status === 429 && retry < 2) {
      const retryAfter = Number(res.headers.get("Retry-After") || 0);
      const msg =
        (data && (data.message || data.detail || data.error))
        || (typeof data === "string" ? data : "");

      const wait = retryAfter || parseRetrySeconds(msg) || 1;
      await sleep(wait * 1000);

      return http(url, opts, retry + 1);
    }

    if (!res.ok) {
      const msg =
        (data && (data.message || data.detail || data.error))
        || (typeof data === "string" ? data : JSON.stringify(data));

      throw new Error(msg || ("HTTP " + res.status));
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

  function asText(v, fallback = "") {
    if (v === null || v === undefined) return fallback;
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return String(v);

    try {
      if (typeof v === "object") {
        if ("label" in v) return asText(v.label, fallback);
        if ("name" in v) return asText(v.name, fallback);
        if ("title" in v) return asText(v.title, fallback);
        if ("value" in v) return asText(v.value, fallback);
        if ("score" in v) return asText(v.score, fallback);
        if ("level" in v) return asText(v.level, fallback);
        return JSON.stringify(v);
      }
    } catch (e) {}

    return fallback;
  }

  function pickFirst(obj, keys, fallback = null) {
    for (const k of keys) {
      const v = obj?.[k];
      if (v !== undefined && v !== null && v !== "") return v;
    }
    return fallback;
  }

  function fmtTime(iso) {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleString("vi-VN");
    } catch (e) {
      return iso;
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

  function normalizeScope() {
    if (STATE.scope.scope === "company" && !STATE.scope.company_id) STATE.scope.scope = "tenant";
    if (STATE.scope.scope === "shop" && !STATE.scope.shop_id) STATE.scope.scope = "tenant";
    if (STATE.scope.scope === "project" && !STATE.scope.project_id) STATE.scope.scope = "tenant";
  }

  function scopeParams() {
    normalizeScope();

    const p = new URLSearchParams();
    p.set("scope", STATE.scope.scope || "tenant");

    const tenantId =
      String(window.HT_TENANT_ID || "").trim() ||
      String(localStorage.getItem("ht_tenant_id") || "").trim();

    if (tenantId) {
      p.set("tenant_id", tenantId);
    }

    if (STATE.scope.company_id) p.set("company_id", STATE.scope.company_id);
    if (STATE.scope.shop_id) p.set("shop_id", STATE.scope.shop_id);
    if (STATE.scope.project_id) p.set("project_id", STATE.scope.project_id);

    return p;
  }
  function renderCurrentShopNotice() {
    const shopId = getCurrentShopId();
    const shops = getKnownShops();
    const found = shops.find((x) => String(x.id) === String(shopId));

    const els = [
      document.getElementById("shopScopeNotice"),
      document.getElementById("shopScopeNoticeSales"),
    ].filter(Boolean);

    els.forEach((el) => {
      if (!shopId) {
        el.innerHTML = `<span style="color:#f87171;font-weight:600;">Chưa chọn shop. Anh chọn shop trước khi nhập dữ liệu nha.</span>`;
      } else {
        el.innerHTML = `<span style="color:#86efac;">Đang thao tác cho shop <b>${escapeHtml(found?.name || ("#" + shopId))}</b></span>`;
      }
    });

    const hasShop = !!shopId;
    const importBtn = document.querySelector('button[onclick="importProductCsv()"]');
    const salesBtn = document.querySelector('button[onclick="submitSales()"]');

    if (importBtn) importBtn.disabled = !hasShop;
    if (salesBtn) salesBtn.disabled = !hasShop;

    renderQuickShopSelector();
  }
  function getCurrentShopId() {
    const shopId =
      String(STATE?.scope?.shop_id || "").trim() ||
      String(localStorage.getItem("ht_shop_id") || "").trim();

    return shopId || "";
  }
  function getKnownShops() {
    const homeShops = ((STATE.raw.home || {}).blocks || {}).shops_health || [];
    const result = [];

    homeShops.forEach((s) => {
      const shopId =
        s.shop_id ??
        s.id ??
        (s.shop && s.shop.id) ??
        "";

      const shopName =
        s.shop_name ||
        s.name ||
        (s.shop && s.shop.name) ||
        (shopId ? `Shop #${shopId}` : "");

      if (shopId) {
        result.push({
          id: String(shopId),
          name: String(shopName || `Shop #${shopId}`),
        });
      }
    });

    const map = new Map();
    result.forEach((x) => {
      map.set(String(x.id), x);
    });

    return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name));
  }
  function renderQuickShopSelector() {
    const el = document.getElementById("shopQuickSelector");
    if (!el) return;

    const shops = getKnownShops();
    const currentShopId = getCurrentShopId();

    let html = `<option value="">-- Chọn shop để nhập dữ liệu --</option>`;

    shops.forEach((shop) => {
      const selected = String(shop.id) === String(currentShopId) ? "selected" : "";
      html += `<option value="${escapeHtml(shop.id)}" ${selected}>${escapeHtml(shop.name)}</option>`;
    });

    el.innerHTML = html;
  }
  function applyQuickShopSelection() {
    const el = document.getElementById("shopQuickSelector");
    if (!el) return;

    const shopId = String(el.value || "").trim();

    if (!shopId) {
      alert("Anh chọn shop trước nha");
      return;
    }

    setScope("shop", {
      shop_id: shopId,
      company_id: "",
      project_id: "",
    });
  }
  function setTheme(theme) {
    STATE.ui.theme = theme === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", STATE.ui.theme);
    localStorage.setItem("ht_theme", STATE.ui.theme);

    const el = $("themeToggle");
    if (el) el.textContent = STATE.ui.theme === "dark" ? "☾" : "☀";
  }

  function applyScopeUI() {
    qsa("#scopeChips .chip").forEach((b) => {
      b.classList.toggle("active", b.dataset.scope === STATE.scope.scope);
    });

    const pill = $("scopePill");
    if (pill) pill.textContent = STATE.scope.scope;
  }

  function setScope(scope, ids = {}) {
    STATE.scope.scope = scope || "tenant";

    if ("company_id" in ids) STATE.scope.company_id = String(ids.company_id || "");
    if ("shop_id" in ids) STATE.scope.shop_id = String(ids.shop_id || "");
    if ("project_id" in ids) STATE.scope.project_id = String(ids.project_id || "");

    localStorage.setItem("ht_scope", STATE.scope.scope);
    localStorage.setItem("ht_company_id", STATE.scope.company_id);
    localStorage.setItem("ht_shop_id", STATE.scope.shop_id);
    localStorage.setItem("ht_project_id", STATE.scope.project_id);

    applyScopeUI();
    renderCurrentShopNotice();
    STATE.timelineCursor = null;
    STATE.lastTimelineIds = new Set();

    safeRefreshAll();
    restartSSE();
  }

  function renderRawJson() {
    const el = $("rawJson");
    if (!el) return;
    el.textContent = JSON.stringify(STATE.raw[STATE.raw.active] || {}, null, 2);
  }

  function renderKPIs(kpis) {
    const el = $("kpis");
    if (!el) return;

    const arr = Array.isArray(kpis) && kpis.length
      ? kpis
      : [
          { k: "Shops", v: 0, s: "Tổng shop" },
          { k: "Risk", v: 0, s: "Shop rủi ro" },
          { k: "Open Tasks", v: 0, s: "Việc đang mở" },
          { k: "Actions", v: 0, s: "Hành động chờ xử lý" },
        ];

    el.innerHTML = "";
    arr.forEach((x) => {
      const div = document.createElement("div");
      div.className = "kpi";
      div.innerHTML = `
        <div class="k">${escapeHtml(x.k)}</div>
        <div class="v">${escapeHtml(x.v)}</div>
        <div class="s">${escapeHtml(x.s || "")}</div>
      `;
      el.appendChild(div);
    });
  }

  function setKpiValueByLabel(label, value) {
    qsa("#kpis .kpi").forEach((c) => {
      const k = c.querySelector(".k")?.textContent?.trim()?.toLowerCase();
      if (k === String(label).toLowerCase()) {
        const v = c.querySelector(".v");
        if (v) v.textContent = String(value);
      }
    });
  }

  function updateHeadline(headline) {
    if (!headline) return;
    setKpiValueByLabel("Shops", headline.shops_total ?? 0);
    setKpiValueByLabel("Risk", headline.shops_risk ?? 0);
    setKpiValueByLabel("Open Tasks", headline.work_open ?? 0);
    setKpiValueByLabel("Actions", headline.actions_open ?? 0);
  }

  function renderTimeline(items) {
    const list = $("timelineList");
    if (!list) return;

    if (!items || !items.length) {
      list.innerHTML = `
        <div class="item">
          <div class="t">Không có sự kiện</div>
          <div class="d">Chưa có dữ liệu timeline.</div>
        </div>
      `;
      return;
    }

    list.innerHTML = "";
    items.forEach((it) => {
      const div = document.createElement("div");
      div.className = "item";
      div.innerHTML = `
        <div class="t">${escapeHtml(it.tieu_de || it.title || "Sự kiện hệ thống")}</div>
        <div class="d">${escapeHtml(it.noi_dung || it.body || it.loai || "")}</div>
        <div class="row">
          <span>${escapeHtml(fmtTime(it.thoi_gian || it.created_at || it.time))}</span>
          <span>${escapeHtml(it?.doi_tuong?.loai || it.kind || "")}</span>
        </div>
      `;
      list.appendChild(div);
    });
  }

  function appendTimeline(items) {
    const list = $("timelineList");
    if (!list) return;

    items.forEach((it) => {
      const key = String(it.id);
      if (STATE.lastTimelineIds.has(key)) return;

      STATE.lastTimelineIds.add(key);

      const div = document.createElement("div");
      div.className = "item";
      div.innerHTML = `
        <div class="t">${escapeHtml(it.tieu_de || it.title || "Sự kiện hệ thống")}</div>
        <div class="d">${escapeHtml(it.noi_dung || it.body || it.loai || "")}</div>
        <div class="row">
          <span>${escapeHtml(fmtTime(it.thoi_gian || it.created_at || it.time))}</span>
          <span>${escapeHtml(it?.doi_tuong?.loai || it.kind || "")}</span>
        </div>
      `;
      list.appendChild(div);
    });
  }

  function renderNotifications(resp) {
    const list = $("notifList");
    if (!list) return;

    const unread = resp?.unread_count || 0;

    if ($("notifBadge")) $("notifBadge").textContent = unread;
    if ($("bbDot")) $("bbDot").classList.toggle("show", unread > 0);

    const items = resp?.items || [];

    if (!items.length) {
      list.innerHTML = `
        <div class="item">
          <div class="t">Không có thông báo</div>
          <div class="d">Mọi thứ đang ổn.</div>
        </div>
      `;
      return;
    }

    list.innerHTML = "";
    items.forEach((n) => {
      const div = document.createElement("div");
      div.className = "item";
      div.innerHTML = `
        <div class="t">${escapeHtml(n.tieu_de || "Thông báo")}</div>
        <div class="d">${escapeHtml(n.noi_dung || "")}</div>
        <div class="row">
          <span>${escapeHtml(fmtTime(n.created_at || n.thoi_gian))}</span>
          <span>${escapeHtml(n.severity || n.muc_do || n.status || "")}</span>
        </div>
        <div class="act">
          <button class="mini mark-read-btn" data-id="${escapeHtml(n.id)}" type="button">Đánh dấu đã đọc</button>
        </div>
      `;
      list.appendChild(div);
    });
  }

  function renderHealth(items) {
    const el = $("healthTable");
    if (!el) return;

    const rows = Array.isArray(items) ? items : [];

    if (!rows.length) {
      el.innerHTML = `
        <div class="trow">
          <div>—</div>
          <div class="muted">No data</div>
          <div class="muted">—</div>
          <div class="muted">—</div>
        </div>
      `;
      return;
    }

    el.innerHTML = "";

    rows.slice(0, 10).forEach((s) => {
      const shopObj = s.shop || s.shop_info || null;

      const shopName =
        pickFirst(s, ["shop_name", "name"], "") ||
        pickFirst(shopObj, ["name", "title"], "") ||
        ("Shop #" + asText(pickFirst(s, ["shop_id", "id"], ""), ""));

      const shopId =
        pickFirst(s, ["shop_id"], null) ??
        pickFirst(shopObj, ["id"], null) ??
        "";

      const healthObj = s.health || s.health_score || s.risk || s.snapshot || null;

      let status =
        pickFirst(s, ["level", "status"], null) ??
        pickFirst(healthObj, ["level", "status", "risk_level"], null) ??
        "unknown";

      status = asText(status, "unknown");

      let score =
        pickFirst(s, ["score", "health", "health_score"], null) ??
        pickFirst(healthObj, ["score", "value", "health", "health_score"], null) ??
        "";

      score = asText(score, "");

      const updated =
        pickFirst(s, ["updated_at", "generated_at", "thoi_gian", "time"], null) ??
        pickFirst(healthObj, ["updated_at", "generated_at", "time"], null) ??
        "";

      const div = document.createElement("div");
      div.className = "trow";
      div.innerHTML = `
        <div>
          <div style="font-weight:850">${escapeHtml(asText(shopName, "Shop"))}</div>
          <div class="muted">id: ${escapeHtml(asText(shopId, ""))}</div>
        </div>
        <div><span class="tag">${escapeHtml(asText(status, "unknown"))}</span></div>
        <div><span class="tag">${escapeHtml(asText(score, ""))}</span></div>
        <div class="muted">${escapeHtml(fmtTime(updated))}</div>
      `;
      el.appendChild(div);
    });
  }

  function renderStrategies(items) {
      const el = $("strategyList");
      if (!el) return;

      const arr = Array.isArray(items) ? items : [];

      if (!arr.length) {
        el.innerHTML = `
          <div class="item">
            <div class="t">Chưa có chiến lược</div>
            <div class="d">Strategy engine sẽ bơm kế hoạch theo rủi ro và mục tiêu.</div>
          </div>
        `;
        return;
      }

      el.innerHTML = "";
      arr.slice(0, 10).forEach((p) => {
        const div = document.createElement("div");
        div.className = "item";
        div.innerHTML = `
          <div class="t">${escapeHtml(p.title || p.ten || "Strategy")}</div>
          <div class="d">${escapeHtml(p.summary || p.mo_ta || p.message || "")}</div>
          <div class="row">
            <span>${escapeHtml(p.priority || "")}</span>
            <span>${escapeHtml(p.kind || "")}</span>
          </div>
        `;
        el.appendChild(div);
      });
    }
    function renderContractWork(data) {
      const workPanel = $("workPanel");
      if (!workPanel) return;

      let box = $("contractWorkBox");
      if (!box) {
        box = document.createElement("div");
        box.id = "contractWorkBox";
        box.className = "card";
        box.style.marginTop = "0";
        box.style.marginBottom = "12px";
        box.innerHTML = `
          <div class="card-h">
            <div>
              <div class="card-t">Việc từ hợp đồng</div>
              <div class="muted">Các việc phát sinh từ payment / milestone / booking</div>
            </div>
          </div>
          <div class="card-b">
            <div id="contractWorkSummary" class="muted" style="margin-bottom:10px;"></div>
            <div id="contractWorkList"></div>
          </div>
        `;
      }

      // ÉP block này nằm NGAY TRƯỚC workPanel (cột trái chính)
      const parent = workPanel.parentNode;
      if (parent && box.parentNode !== parent) {
        parent.insertBefore(box, workPanel);
      } else if (parent && box.nextSibling !== workPanel) {
        parent.insertBefore(box, workPanel);
      }

      const summaryEl = $("contractWorkSummary");
      const listEl = $("contractWorkList");
      if (!summaryEl || !listEl) return;

      const headline = data?.headline || {};
      const items = Array.isArray(data?.items) ? data.items : [];

      summaryEl.innerHTML = `
        Tổng việc mở: <b>${headline.contract_work_open || 0}</b> •
        Quá hạn: <b>${headline.contract_work_overdue || 0}</b> •
        Gấp: <b>${headline.contract_work_urgent || 0}</b>
      `;

      if (!items.length) {
        listEl.innerHTML = `
          <div class="item">
            <div class="t">Chưa có việc từ hợp đồng</div>
            <div class="d">Hiện chưa có payment / milestone / booking nào cần xử lý.</div>
          </div>
        `;
        return;
      }

      listEl.innerHTML = "";

      items.forEach((x) => {
        const div = document.createElement("div");
        div.className = "item";
        div.innerHTML = `
          <div class="t is-clickable" data-open-task="${escapeHtml(x.id)}">${escapeHtml(x.title || "Task hợp đồng")}</div>
          <div class="d">${escapeHtml(x.description || "")}</div>
          <div class="row">
            <span>Trạng thái: ${escapeHtml(x.status || "todo")}</span>
            <span>Ưu tiên: ${escapeHtml(x.priority || 0)}</span>
            <span>Loại: ${escapeHtml(x.target_type || "")}</span>
            <span>Deadline: ${escapeHtml(fmtTime(x.due_at) || "-")}</span>
          </div>
        `;
        listEl.appendChild(div);
      });
    }
    function timelineIcon(kind){
      if(kind === "contract_payment") return "💰";
      if(kind === "contract_milestone") return "📌";
      if(kind === "contract_booking_item") return "🎬";
      return "📄";
    }
    function renderContractTimeline(data) {
      const contractWorkBox = $("contractWorkBox");
      if (!contractWorkBox) return;

      let box = $("contractTimelineBox");
      if (!box) {
        box = document.createElement("div");
        box.id = "contractTimelineBox";
        box.className = "card";
        box.style.marginTop = "12px";
        box.innerHTML = `
          <div class="card-h">
            <div>
              <div class="card-t">Timeline hợp đồng</div>
              <div class="muted">Theo dõi payment / milestone / booking theo vòng đời</div>
            </div>
          </div>
          <div class="card-b">
            <div id="contractTimelineSummary" class="muted" style="margin-bottom:10px;"></div>
            <div id="contractTimelineList"></div>
          </div>
        `;
        contractWorkBox.parentNode.insertBefore(box, contractWorkBox.nextSibling);
      }

      const summaryEl = $("contractTimelineSummary");
      const listEl = $("contractTimelineList");
      if (!summaryEl || !listEl) return;

      const headline = data?.headline || {};
      const items = Array.isArray(data?.items) ? data.items : [];

      summaryEl.innerHTML = `
        Tổng mốc: <b>${headline.contract_timeline_total || 0}</b> •
        Critical: <b>${headline.contract_timeline_critical || 0}</b> •
        Warning: <b>${headline.contract_timeline_warning || 0}</b> •
        Info: <b>${headline.contract_timeline_info || 0}</b>
      `;

      if (!items.length) {
        listEl.innerHTML = `
          <div class="item">
            <div class="t">Chưa có timeline hợp đồng</div>
            <div class="d">Hiện chưa có payment / milestone / booking trong vòng 14 ngày tới.</div>
          </div>
        `;
        return;
      }

      listEl.innerHTML = "";

      items.forEach((x) => {
        const div = document.createElement("div");
        div.className = "item";
        div.innerHTML = `
          <div class="t is-clickable" data-open-task="${escapeHtml(x.target_id || "")}">${timelineIcon(x.kind)} ${escapeHtml(x.title || "Timeline hợp đồng")}</div>
          <div class="d">${escapeHtml(x.summary || "")}</div>
          <div class="row">
            <span>Loại: ${escapeHtml(x.kind || "")}</span>
            <span class="priority-${escapeHtml(x.priority || "info")}">
            Mức độ: ${escapeHtml(x.priority || "")}
            </span>
            <span>Hợp đồng: ${escapeHtml(x.contract_code || "")}</span>
            <span>Hạn: ${escapeHtml(fmtTime(x.due_at) || "-")}</span>
          </div>
        `;
        listEl.appendChild(div);
      });
    }
  function renderKernel(data) {
    const el = $("kernelTable");
    if (!el) return;

    const qd = data?.quyet_dinh || {};
    const risks = Array.isArray(data?.rui_ro) ? data.rui_ro : [];

    let strategyCount = 0;
    if (Array.isArray(data?.chien_luoc)) strategyCount = data.chien_luoc.length;
    else if (Array.isArray(data?.chien_luoc?.items)) strategyCount = data.chien_luoc.items.length;
    else if (Array.isArray(data?.chien_luoc?.plans)) strategyCount = data.chien_luoc.plans.length;

    const rows = [
      ["Tenant", data?.tenant_id ?? "-"],
      ["Role", data?.role || "-"],
      ["Scope", data?.scope || "-"],
      ["Generated", fmtTime(data?.generated_at)],
      ["Decision alerts", Array.isArray(qd?.canh_bao) ? qd.canh_bao.length : 0],
      ["Decision recommendations", Array.isArray(qd?.goi_y) ? qd.goi_y.length : 0],
      ["Decision actions", Array.isArray(qd?.hanh_dong) ? qd.hanh_dong.length : 0],
      ["Risks", risks.length],
      ["Strategies", strategyCount],
      ["Contract payment overdue", data?.headline?.contract_payment_overdue ?? 0],
      ["Contract payment due soon", data?.headline?.contract_payment_due_soon ?? 0],
      ["Contract milestone overdue", data?.headline?.contract_milestone_overdue ?? 0],
      ["Contract milestone due soon", data?.headline?.contract_milestone_due_soon ?? 0],
      ["Booking payout overdue", data?.headline?.booking_payout_overdue ?? 0],
      ["Booking payout due soon", data?.headline?.booking_payout_due_soon ?? 0],
      ["Booking air soon", data?.headline?.booking_air_soon ?? 0],
      ["Booking air passed no link", data?.headline?.booking_air_passed_no_link ?? 0],
      ["Contract work open", data?.headline?.contract_work_open ?? 0],
      ["Contract work overdue", data?.headline?.contract_work_overdue ?? 0],
      ["Contract work urgent", data?.headline?.contract_work_urgent ?? 0],
      ["Realtime", $("rtPill")?.textContent || "-"],
    ];

    el.innerHTML = "";
    rows.forEach(([k, v]) => {
      const div = document.createElement("div");
      div.className = "trow";
      div.innerHTML = `
        <div style="font-weight:800">${escapeHtml(k)}</div>
        <div class="muted" style="grid-column: span 3;">${escapeHtml(asText(v, "-"))}</div>
      `;
      el.appendChild(div);
    });
  }

    function priorityInfo(priority) {
      const p = Number(priority || 2);
      if (p === 1) return { text: "Ưu tiên thấp", cls: "p-low" };
      if (p === 2) return { text: "Ưu tiên vừa", cls: "p-normal" };
      if (p === 3) return { text: "Ưu tiên cao", cls: "p-high" };
      if (p === 4) return { text: "Ưu tiên gấp", cls: "p-urgent" };
      return { text: "Ưu tiên", cls: "p-normal" };
    }

    function deadlineInfo(iso, status) {
      if (!iso) return { text: "Chưa có deadline", cls: "deadline-ok" };

      try {
        const due = new Date(iso);
        const now = new Date();

        if (String(status || "").toLowerCase() === "done") {
          return { text: "Đã hoàn thành", cls: "deadline-ok" };
        }

        const diffHours = (due.getTime() - now.getTime()) / 36e5;

        if (diffHours < 0) return { text: "Đã quá hạn", cls: "deadline-overdue" };
        if (diffHours <= 24) return { text: "Sắp tới hạn", cls: "deadline-soon" };
        return { text: "Đúng tiến độ", cls: "deadline-ok" };
      } catch (e) {
        return { text: "Deadline không hợp lệ", cls: "deadline-overdue" };
      }
    }

    function taskMetaText(t) {
      const assigneeText =
        t.assignee_name
          ? `${t.assignee_name}${t.assignee_email ? " • " + t.assignee_email : ""}`
          : (t.assignee_email || (t.assignee_id ? `User #${t.assignee_id}` : "Chưa giao"));

      const companyText = t.company_name || (t.company_id ? `#${t.company_id}` : "-");
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
        companyText,
        shopText,
        projectText,
        priorityText: priorityMap[t.priority] || t.priority || "-",
      };
    }

    function buildAllWork() {
      const map = new Map();

      [
        ...(STATE.work.open || []),
        ...(STATE.work.todo || []),
        ...(STATE.work.doing || []),
        ...(STATE.work.blocked || []),
        ...(STATE.work.done || []),
      ].forEach((x) => {
        map.set(String(x.id), x);
      });

      STATE.work.all = Array.from(map.values());
    }

    function findTaskById(taskId) {
      return STATE.work.all.find((x) => String(x.id) === String(taskId)) || null;
    }

    function matchWorkFilter(task) {
      const assignee = (STATE.work.filters.assignee || "").trim().toLowerCase();
      const keyword = (STATE.work.filters.keyword || "").trim().toLowerCase();
      const company = (STATE.work.filters.company || "").trim().toLowerCase();
      const shop = (STATE.work.filters.shop || "").trim().toLowerCase();
      const status = (STATE.work.filters.status || "").trim().toLowerCase();

      const assigneeHay = `${task.assignee_name || ""} ${task.assignee_email || ""} ${task.assignee_id || ""}`.toLowerCase();
      const keywordHay = [
        task.title,
        task.description,
        task.assignee_name,
        task.assignee_email,
        task.company_name,
        task.shop_name,
        task.project_name,
      ].filter(Boolean).join(" ").toLowerCase();
      const companyHay = `${task.company_name || ""} ${task.company_id || ""}`.toLowerCase();
      const shopHay = `${task.shop_name || ""} ${task.shop_id || ""}`.toLowerCase();
      const statusHay = `${task.status || ""}`.toLowerCase();

      if (assignee && !assigneeHay.includes(assignee)) return false;
      if (keyword && !keywordHay.includes(keyword)) return false;
      if (company && !companyHay.includes(company)) return false;
      if (shop && !shopHay.includes(shop)) return false;
      if (status && statusHay !== status) return false;

      return true;
    }

    function filteredTasks(items) {
      return (Array.isArray(items) ? items : []).filter(matchWorkFilter);
    }
    function ensureWorkToolbar() {
    const workPanel = $("workPanel");
    if (!workPanel) return;

    const cardBody = qs(".card-b", workPanel) || workPanel;
    if (!cardBody) return;

    if (!$("workToolbarFinal")) {
      const div = document.createElement("div");
      div.id = "workToolbarFinal";
      div.style.marginBottom = "12px";
      div.innerHTML = `
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:10px;">
          <input id="filterAssigneeFinal" class="input" placeholder="Lọc người phụ trách" style="min-width:220px; flex:1;">
          <input id="filterKeywordFinal" class="input" placeholder="Tìm tiêu đề / mô tả / email" style="min-width:220px; flex:1;">
          <input id="filterCompanyFinal" class="input" placeholder="Lọc công ty" style="min-width:180px; flex:1;">
          <input id="filterShopFinal" class="input" placeholder="Lọc shop" style="min-width:180px; flex:1;">
          <select id="filterStatusFinal" class="input" style="min-width:180px;">
            <option value="">Tất cả trạng thái</option>
            <option value="todo">todo</option>
            <option value="doing">doing</option>
            <option value="blocked">blocked</option>
            <option value="done">done</option>
            <option value="cancelled">cancelled</option>
          </select>
          <button id="btnClearFilterFinal" class="btn mini" type="button">Xoá lọc</button>
        </div>

        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:10px;">
          <select id="boardGroupByFinal" class="input" style="min-width:220px;">
            <option value="status">Kanban theo trạng thái</option>
            <option value="company">Kanban theo công ty</option>
            <option value="shop">Kanban theo shop</option>
            <option value="assignee">Kanban theo người phụ trách</option>
          </select>

          <input id="quickDeadlineFinal" class="input" type="datetime-local" style="min-width:220px;">
          <select id="quickPriorityFinal" class="input" style="min-width:180px;">
            <option value="2">Ưu tiên vừa</option>
            <option value="1">Ưu tiên thấp</option>
            <option value="3">Ưu tiên cao</option>
            <option value="4">Ưu tiên gấp</option>
          </select>

          <button id="btnReloadBoardFinal" class="btn mini" type="button">Làm mới board</button>
        </div>

        <div id="workSummaryFinal" class="muted" style="margin-bottom:10px;"></div>
      `;
      cardBody.insertBefore(div, cardBody.firstChild);
    }

    if ($("filterAssigneeFinal")) $("filterAssigneeFinal").value = STATE.work.filters.assignee || "";
    if ($("filterKeywordFinal")) $("filterKeywordFinal").value = STATE.work.filters.keyword || "";
    if ($("filterCompanyFinal")) $("filterCompanyFinal").value = STATE.work.filters.company || "";
    if ($("filterShopFinal")) $("filterShopFinal").value = STATE.work.filters.shop || "";
    if ($("filterStatusFinal")) $("filterStatusFinal").value = STATE.work.filters.status || "";
    if ($("boardGroupByFinal")) $("boardGroupByFinal").value = STATE.ui.boardGroupBy || "status";
  }

  function updateWorkSummary() {
    const box = $("workSummaryFinal");
    if (!box) return;

    const arr = filteredTasks(STATE.work.all);
    const total = arr.length;
    const todo = arr.filter((x) => x.status === "todo").length;
    const doing = arr.filter((x) => x.status === "doing").length;
    const blocked = arr.filter((x) => x.status === "blocked").length;
    const done = arr.filter((x) => x.status === "done").length;
    const overdue = arr.filter((x) => {
      return x.due_at &&
        new Date(x.due_at).getTime() < Date.now() &&
        !["done", "cancelled"].includes(String(x.status || "").toLowerCase());
    }).length;

    box.innerHTML = `
      Tổng việc: <b>${total}</b> •
      Todo: <b>${todo}</b> •
      Doing: <b>${doing}</b> •
      Blocked: <b>${blocked}</b> •
      Done: <b>${done}</b> •
      Quá hạn: <b>${overdue}</b>
    `;
  }

  function renderWorkInbox(resp) {
    const el = $("workList");
    if (!el) return;

        const items = filteredTasks(resp?.items || []).sort((a, b) => {
          const aContract = ["contract_payment", "contract_milestone", "contract_booking_item"].includes(String(a.target_type || ""));
          const bContract = ["contract_payment", "contract_milestone", "contract_booking_item"].includes(String(b.target_type || ""));

          if (aContract && !bContract) return -1;
          if (!aContract && bContract) return 1;

          const ap = Number(a.priority || 0);
          const bp = Number(b.priority || 0);
          if (bp !== ap) return bp - ap;

          const ad = a.due_at ? new Date(a.due_at).getTime() : Number.MAX_SAFE_INTEGER;
          const bd = b.due_at ? new Date(b.due_at).getTime() : Number.MAX_SAFE_INTEGER;
          return ad - bd;
        });

    if (!items.length) {
      el.innerHTML = `
        <div class="item">
          <div class="t">Chưa có việc</div>
          <div class="d">Bấm <b>+ Việc mới</b> để tạo task đầu tiên.</div>
        </div>
      `;
      return;
    }

    el.innerHTML = "";

    items.forEach((t) => {
      const meta = taskMetaText(t);

      const div = document.createElement("div");
      div.className = "witem";
      div.dataset.id = t.id;
      div.draggable = true;

      div.innerHTML = `
        <div class="wtop">
          <div>
            <div class="wtitle is-clickable" data-open-task="${escapeHtml(t.id)}">${escapeHtml(t.title || ("Task #" + t.id))}</div>
            <div class="wmeta">
              <span>ID: ${escapeHtml(t.id)}</span>
              <span>Trạng thái: ${escapeHtml(t.status || "todo")}</span>
              <span>Ưu tiên: ${escapeHtml(meta.priorityText)}</span>
              <span>Người nhận: ${escapeHtml(meta.assigneeText)}</span>
              <span>Công ty: ${escapeHtml(meta.companyText)}</span>
              <span>Shop: ${escapeHtml(meta.shopText)}</span>
              <span>Dự án: ${escapeHtml(meta.projectText)}</span>
              <span>Deadline: ${escapeHtml(fmtTime(t.due_at) || "-")}</span>
            </div>
            ${t.description ? `<div class="d" style="margin-top:8px;">${escapeHtml(t.description)}</div>` : ""}
          </div>

          <div class="wact">
            <select class="statusSel" data-id="${escapeHtml(t.id)}">
              <option value="todo" ${t.status === "todo" ? "selected" : ""}>todo</option>
              <option value="doing" ${t.status === "doing" ? "selected" : ""}>doing</option>
              <option value="blocked" ${t.status === "blocked" ? "selected" : ""}>blocked</option>
              <option value="done" ${t.status === "done" ? "selected" : ""}>done</option>
              <option value="cancelled" ${t.status === "cancelled" ? "selected" : ""}>cancelled</option>
            </select>
            <button class="mini moveBtn" data-id="${escapeHtml(t.id)}" type="button">Move</button>
          </div>
        </div>

        <div class="act" style="display:flex; gap:8px; margin-top:10px; flex-wrap:wrap;">
          <input class="input" style="min-width:140px;" placeholder="assignee_id" data-assign-id="${escapeHtml(t.id)}" />
          <input class="input" style="min-width:220px;" placeholder="email / username" data-assign-by="${escapeHtml(t.id)}" />
          <button class="mini assignBtn" data-id="${escapeHtml(t.id)}" type="button">Assign</button>
        </div>
      `;

      div.addEventListener("dragstart", (e) => {
            STATE.dragTaskId = String(t.id);
            e.dataTransfer.setData("text/plain", String(t.id));
            e.dataTransfer.effectAllowed = "move";
            div.classList.add("dragging");
          });

          div.addEventListener("dragend", () => {
            div.classList.remove("dragging");
            STATE.dragTaskId = null;
          });

          el.appendChild(div);
        });
      }

  function makeBoardCard(t) {
    const meta = taskMetaText(t);

    return `
      <div class="kcard v12" data-id="${escapeHtml(t.id)}" draggable="true">
        <div class="ktitle is-clickable" data-open-task="${escapeHtml(t.id)}">${escapeHtml(t.title || ("Task #" + t.id))}</div>

        <div class="kmeta">
          <span>#${escapeHtml(t.id)}</span>
          <span>${escapeHtml(meta.priorityText)}</span>
          <span>${escapeHtml(t.status || "-")}</span>
        </div>

        <div class="kmeta">
          <span>Người phụ trách: ${escapeHtml(meta.assigneeText)}</span>
        </div>

        <div class="kmeta">
          <span>Công ty: ${escapeHtml(meta.companyText)}</span>
          <span>Shop: ${escapeHtml(meta.shopText)}</span>
          <span>Dự án: ${escapeHtml(meta.projectText)}</span>
        </div>

        ${t.description ? `<div class="kdesc">${escapeHtml(t.description)}</div>` : ""}

        <div class="kmeta">
          <span>Deadline: ${escapeHtml(fmtTime(t.due_at) || "-")}</span>
        </div>

        <div class="kact" style="display:flex; gap:8px; flex-wrap:wrap;">
          <select class="kb-status" data-id="${escapeHtml(t.id)}">
            <option value="todo" ${t.status === "todo" ? "selected" : ""}>todo</option>
            <option value="doing" ${t.status === "doing" ? "selected" : ""}>doing</option>
            <option value="blocked" ${t.status === "blocked" ? "selected" : ""}>blocked</option>
            <option value="done" ${t.status === "done" ? "selected" : ""}>done</option>
            <option value="cancelled" ${t.status === "cancelled" ? "selected" : ""}>cancelled</option>
          </select>

          <select class="kb-priority" data-id="${escapeHtml(t.id)}">
            <option value="1" ${Number(t.priority) === 1 ? "selected" : ""}>Thấp</option>
            <option value="2" ${Number(t.priority || 2) === 2 ? "selected" : ""}>Vừa</option>
            <option value="3" ${Number(t.priority) === 3 ? "selected" : ""}>Cao</option>
            <option value="4" ${Number(t.priority) === 4 ? "selected" : ""}>Gấp</option>
          </select>

          <button class="mini kb-move-btn" data-id="${escapeHtml(t.id)}" type="button">Move</button>
          <button class="mini kb-edit-open-btn" data-id="${escapeHtml(t.id)}" type="button">Sửa nhanh</button>
        </div>

        <div class="kb-inline-edit" data-edit-box="${escapeHtml(t.id)}" style="display:none; margin-top:10px;">
          <input class="input kb-edit-title" data-id="${escapeHtml(t.id)}" value="${escapeHtml(t.title || "")}" style="margin-bottom:8px;">
          <textarea class="input kb-edit-desc" data-id="${escapeHtml(t.id)}" style="min-height:84px; margin-bottom:8px;">${escapeHtml(t.description || "")}</textarea>
          <input class="input kb-edit-deadline" data-id="${escapeHtml(t.id)}" type="datetime-local" value="${escapeHtml(toDatetimeLocal(t.due_at))}" style="margin-bottom:8px;">
          <div style="display:flex; gap:8px;">
            <button class="btn mini kb-save-btn" data-id="${escapeHtml(t.id)}" type="button">Lưu</button>
            <button class="btn mini kb-cancel-btn" data-id="${escapeHtml(t.id)}" type="button">Huỷ</button>
          </div>
        </div>
      </div>
    `;
  }
  
  function makeQuickCreateBox(groupType, groupKey, label) {
    return `
      <div class="kb-quick-create" style="display:flex; gap:8px; margin-bottom:10px;">
        <input
          class="input kb-col-create-title"
          data-group-type="${escapeHtml(groupType)}"
          data-group-key="${escapeHtml(groupKey)}"
          placeholder="${escapeHtml(label)}"
          style="flex:1;"
        >
        <button
          class="btn mini kb-col-create-btn"
          data-group-type="${escapeHtml(groupType)}"
          data-group-key="${escapeHtml(groupKey)}"
          type="button"
        >Tạo</button>
      </div>
    `;
  }

  function renderBoardStatusMode(items) {
    const board = $("workBoard");
    if (!board) return;

    const cols = {
      todo: items.filter(x => x.status === "todo"),
      doing: items.filter(x => x.status === "doing"),
      blocked: items.filter(x => x.status === "blocked"),
      done: items.filter(x => x.status === "done"),
    };

    const makeCol = (key, label) => `
      <div class="kanban-col">
        <div class="kanban-head">
          <span>${label}</span>
          <span class="pill">${cols[key].length}</span>
        </div>

        ${makeQuickCreateBox("status", key, `Tạo nhanh việc ở cột ${label}...`)}

        <div class="kanban-list" data-drop-type="status" data-drop-key="${key}">
          ${
            cols[key].length
              ? cols[key].map(makeBoardCard).join("")
              : `<div class="kanban-empty">Chưa có việc</div>`
          }
        </div>
      </div>
    `;

    board.innerHTML = `
      ${makeCol("todo", "Todo")}
      ${makeCol("doing", "Doing")}
      ${makeCol("blocked", "Blocked")}
      ${makeCol("done", "Done")}
    `;
  }

  function renderBoardGroupMode(items, mode) {
    const board = $("workBoard");
    if (!board) return;

    const groups = {};

    items.forEach((t) => {
      let key = "Chưa phân nhóm";

      if (mode === "company") {
        key = t.company_name || (t.company_id ? `Công ty #${t.company_id}` : "Chưa gắn công ty");
      } else if (mode === "shop") {
        key = t.shop_name || (t.shop_id ? `Shop #${t.shop_id}` : "Chưa gắn shop");
      } else if (mode === "assignee") {
        key = t.assignee_name || t.assignee_email || (t.assignee_id ? `User #${t.assignee_id}` : "Chưa giao");
      }

      if (!groups[key]) groups[key] = [];
      groups[key].push(t);
    });

    const keys = Object.keys(groups).sort((a, b) => a.localeCompare(b));

    if (!keys.length) {
      board.innerHTML = `<div class="kanban-empty">Không có task phù hợp bộ lọc.</div>`;
      return;
    }

    board.innerHTML = keys.map((key) => `
      <div class="kanban-col kanban-col-group">
        <div class="kanban-head">
          <span>${escapeHtml(key)}</span>
          <span class="pill">${groups[key].length}</span>
        </div>

        ${makeQuickCreateBox(mode, key, `Tạo nhanh trong nhóm ${key}...`)}

        <div class="kanban-list" data-drop-type="readonly" data-drop-key="${escapeHtml(key)}">
          ${groups[key].map(makeBoardCard).join("")}
        </div>
      </div>
    `).join("");
  }

  function renderWorkBoard() {
    ensureWorkToolbar();
    updateWorkSummary();

    const items = filteredTasks(STATE.work.all);

    if (STATE.ui.boardGroupBy === "status") {
      renderBoardStatusMode(items);
      bindKanbanDnD(true);
    } else {
      renderBoardGroupMode(items, STATE.ui.boardGroupBy);
      bindKanbanDnD(false);
    }

    qsa(".kcard").forEach((card) => {
      card.addEventListener("dragstart", (e) => {
        const id = card.dataset.id;
        STATE.dragTaskId = String(id);
        e.dataTransfer.setData("text/plain", String(id));
        e.dataTransfer.effectAllowed = "move";
        card.classList.add("dragging");
      });

      card.addEventListener("dragend", () => {
        card.classList.remove("dragging");
        STATE.dragTaskId = null;
      });
    });
  }

  function renderAllWork() {
    renderWorkInbox({ items: STATE.work.open, open_count: STATE.work.open.length });
    renderWorkBoard();
  }

  function switchWorkView(view) {
    STATE.ui.workView = view || "list";
    localStorage.setItem("ht_work_view", STATE.ui.workView);

    const listWrap = $("workListWrap");
    const boardWrap = $("workBoardWrap");

    qsa(".work-view-tab").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === STATE.ui.workView);
    });

    if (listWrap) listWrap.style.display = STATE.ui.workView === "list" ? "" : "none";
    if (boardWrap) boardWrap.style.display = STATE.ui.workView === "board" ? "" : "none";
  }

  function buildPayloadForQuickCreate(groupType, groupKey) {
    const p = scopeParams();
    const payload = {
      priority: Number($("quickPriorityFinal")?.value || 2),
      due_at: ($("quickDeadlineFinal")?.value || "").trim() || null,
    };

    if (p.get("company_id")) payload.company_id = Number(p.get("company_id"));
    if (p.get("shop_id")) payload.shop_id = Number(p.get("shop_id"));
    if (p.get("project_id")) payload.project_id = Number(p.get("project_id"));

    if (groupType === "status") {
      payload.status = groupKey || "todo";
    }

    if (groupType === "company") {
      const matched = STATE.work.all.find((x) => {
        const label = x.company_name || (x.company_id ? `Công ty #${x.company_id}` : "Chưa gắn công ty");
        return label === groupKey;
      });
      if (matched?.company_id) payload.company_id = matched.company_id;
    }

    if (groupType === "shop") {
      const matched = STATE.work.all.find((x) => {
        const label = x.shop_name || (x.shop_id ? `Shop #${x.shop_id}` : "Chưa gắn shop");
        return label === groupKey;
      });
      if (matched?.shop_id) payload.shop_id = matched.shop_id;
      if (matched?.company_id && !payload.company_id) payload.company_id = matched.company_id;
    }

    if (groupType === "assignee") {
      const matched = STATE.work.all.find((x) => {
        const label = x.assignee_name || x.assignee_email || (x.assignee_id ? `User #${x.assignee_id}` : "Chưa giao");
        return label === groupKey;
      });
      if (matched?.assignee_id) payload.assignee_id = matched.assignee_id;
      payload.status = "todo";
    }

    return payload;
  }
  bindQuickCreateInputs();

  async function quickCreateByGroup(groupType, groupKey, inputEl) {
    const title = (inputEl?.value || "").trim();

    if (!title) {
      alert("Nhập tiêu đề công việc");
      return;
    }

    const payload = buildPayloadForQuickCreate(groupType, groupKey);
    payload.title = title;

    await createTask(payload);

    if (inputEl) inputEl.value = "";

    await refreshWorkData();
    await refreshTimeline(true);
    await refreshHome();
  }

  async function refreshWorkData() {
    if (!CFG.workInbox) return;

    const p = scopeParams();
    p.set("page", "1");
    p.set("page_size", "200");
    // KHÔNG set status=all
    // KHÔNG dùng limit vì backend không đọc limit ở endpoint này

    const data = await http(`${CFG.workInbox}?${p.toString()}`);
    const items = Array.isArray(data?.items) ? data.items : [];

    STATE.work.all = items;
    STATE.work.open = items.filter(x => !["done", "cancelled"].includes(String(x.status || "").toLowerCase()));
    STATE.work.todo = items.filter(x => String(x.status || "").toLowerCase() === "todo");
    STATE.work.doing = items.filter(x => String(x.status || "").toLowerCase() === "doing");
    STATE.work.blocked = items.filter(x => String(x.status || "").toLowerCase() === "blocked");
    STATE.work.done = items.filter(x => String(x.status || "").toLowerCase() === "done");

    STATE.raw.work = data;

// KHÔNG overwrite KPI "Open Tasks" ở đây.
// KPI headline phải lấy từ /api/v1/os/home/ hoặc /api/v1/os/dashboard/
    renderAllWork();
    renderRawJson();
  }
  async function refreshTaskComments(taskId) {
    if (!taskId || !CFG.workCommentsBase) return;

    const data = await http(`${CFG.workCommentsBase}${taskId}/comments/`);
    STATE.raw.comments = data;
    renderTaskComments(data?.items || []);
  }
  async function refreshControlCenter() {
    if (!CFG.controlCenter) return;

    const data = await http(`${CFG.controlCenter}?${scopeParams().toString()}`);
    STATE.raw.control = data;

    let kpis = null;

    try {
      const schema = data.schema || data;

      if (schema?.blocks && Array.isArray(schema.blocks)) {
        const kpiBlock = schema.blocks.find((b) => b.type === "kpi" || b.id === "headline");

        if (kpiBlock?.props?.items && Array.isArray(kpiBlock.props.items)) {
          kpis = kpiBlock.props.items.map((x) => ({
            k: x.label || x.key,
            v: x.value ?? 0,
            s: x.sub || "",
          }));
        }
      }
    } catch (e) {}

    renderKPIs(kpis);
    renderRawJson();
  }

  async function refreshTimeline(reset = false) {
    if (!CFG.timeline) return;

    const p = scopeParams();
    p.set("hours", STATE.scope.hours || "24");
    p.set("limit", "50");

    if (!reset && STATE.timelineCursor?.before_ts) p.set("before_ts", STATE.timelineCursor.before_ts);
    if (!reset && STATE.timelineCursor?.before_id) p.set("before_id", String(STATE.timelineCursor.before_id));

    const data = await http(`${CFG.timeline}?${p.toString()}`);
    STATE.raw.timeline = data;

    const items = data.items || [];
    STATE.timelineCursor = data.next_cursor || null;

    if (reset) {
      STATE.lastTimelineIds = new Set(items.map((x) => String(x.id)));
      renderTimeline(items);
    } else {
      appendTimeline(items);
    }

    renderRawJson();
  }

  async function refreshNotifications() {
    if (!CFG.notifications) return;

    const p = scopeParams();
    p.set("status", "new");
    p.set("limit", "20");

    const data = await http(`${CFG.notifications}?${p.toString()}`);
    STATE.raw.notifications = data;
    renderNotifications(data);
    renderRawJson();
  }

  function renderShopQuickNav(data) {
    const healthTable = $("healthTable");
    if (!healthTable || !healthTable.parentNode) return;

    let nav = $("shopNavFinal");
    if (!nav) {
      nav = document.createElement("div");
      nav.id = "shopNavFinal";
      nav.style.display = "flex";
      nav.style.gap = "8px";
      nav.style.flexWrap = "wrap";
      nav.style.marginBottom = "12px";
      healthTable.parentNode.insertBefore(nav, healthTable);
    }

    const shops = ((data?.blocks || {}).shops_health || []).slice(0, 8);

    if (!shops.length) {
      nav.innerHTML = "";
      return;
    }

    nav.innerHTML = shops.map((s) => {
      const shopId = s.shop_id || s.id || "";
      const name = s.shop_name || s.name || ("Shop " + shopId);
      return `
        <button class="btn mini shop-nav-final" data-shop-id="${escapeHtml(shopId)}" type="button">
          ${escapeHtml(name)}
        </button>
      `;
    }).join("");
  }

  async function refreshHome() {
    if (!CFG.home) return;

    const data = await http(`${CFG.home}?${scopeParams().toString()}`);
    STATE.raw.home = data;

    const shops = (data.blocks && data.blocks.shops_health) || [];
    renderHealth(shops);

    let strategies = [];
    if (Array.isArray(data.chien_luoc)) {
      strategies = data.chien_luoc;
    } else if (data.chien_luoc && Array.isArray(data.chien_luoc.items)) {
      strategies = data.chien_luoc.items;
    } else if (data.chien_luoc && Array.isArray(data.chien_luoc.plans)) {
      strategies = data.chien_luoc.plans;
    } else if (data.quyet_dinh && Array.isArray(data.quyet_dinh.goi_y)) {
      strategies = data.quyet_dinh.goi_y.map((x) => ({
        title: x.title || x.ten || "Recommendation",
        summary: x.summary || x.mo_ta || x.message || "",
        priority: x.priority || "",
        kind: x.kind || "decision",
      }));
    }

    updateHeadline(data.headline || {});
    updateHeroStats(data);
    renderMissionControl((data.blocks && data.blocks.mission_control) || {});
    renderFounderDashboard((data.blocks && data.blocks.founder_dashboard) || {});
    renderShopRiskRadar((data.blocks && data.blocks.shop_risk_radar) || {});
    renderCashflowRadar((data.blocks && data.blocks.cashflow_radar) || {});
    renderRevenuePrediction((data.blocks && data.blocks.revenue_prediction) || {});
    renderAIDecisions((data.blocks && data.blocks.ai_decisions) || {});
    renderContractHealthScore((data.blocks && data.blocks.contract_health_score) || {});
    renderAgencyHealth((data.blocks && data.blocks.agency_health) || {});
    renderShopBrain((data.blocks && data.blocks.shop_brain) || {})
    renderProductRadar((data.blocks && data.blocks.product_radar) || {});
    renderShopServicesOverview((data.blocks && data.blocks.shop_services_overview) || {});
    renderShopServiceTimeline((data.blocks && data.blocks.shop_service_timeline) || {});
    renderShopKPIStrip((data.blocks && data.blocks.shop_kpi_strip) || {});
    renderSKURadar((data.blocks && data.blocks.sku_radar) || {});
    renderShopMissionDigest((data.blocks && data.blocks.shop_mission_digest) || {});
    renderShopCommandCenter((data.blocks && data.blocks.shop_command_center) || {});
    renderShopAIActions((data.blocks && data.blocks.shop_ai_actions) || {});
    renderStrategies(strategies);
    renderContractWork((data.blocks && data.blocks.contract_work) || {});
    renderContractTimeline((data.blocks && data.blocks.contract_timeline) || {});
    renderContractRadar(data.blocks?.contract_radar);
    renderKernel(data);
    renderShopQuickNav(data);
    renderQuickShopSelector();
    renderCurrentShopNotice();
    ensureOSQuickLinks();
    syncOSQuickLinksByScroll();
    renderRawJson();

  }
    async function createTask(payload) {
    if (!CFG.workCreate) throw new Error("Thiếu CFG.workCreate");

    return http(CFG.workCreate, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
  }
  function getStatusColumnItems(status) {
    return STATE.work.all
      .filter((x) => String(x.status || "").toLowerCase() === String(status || "").toLowerCase())
      .sort((a, b) => {
        const ra = String(a.rank || "");
        const rb = String(b.rank || "");
        if (ra < rb) return -1;
        if (ra > rb) return 1;
        return Number(a.id) - Number(b.id);
      });
  }

  function calcDropPosition(col, draggedId) {
    const cards = qsa(".kcard", col).filter((x) => String(x.dataset.id) !== String(draggedId));
    if (!cards.length) return 1;

    const y = window.__HT_LAST_DROP_Y__ || 0;
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
  function patchTaskLocal(taskId, patch = {}) {
    const id = String(taskId);

    STATE.work.all = STATE.work.all.map((x) =>
      String(x.id) === id ? { ...x, ...patch } : x
    );

    STATE.work.open = STATE.work.all.filter(
      (x) => !["done", "cancelled"].includes(String(x.status || "").toLowerCase())
    );
    STATE.work.todo = STATE.work.all.filter(
      (x) => String(x.status || "").toLowerCase() === "todo"
    );
    STATE.work.doing = STATE.work.all.filter(
      (x) => String(x.status || "").toLowerCase() === "doing"
    );
    STATE.work.blocked = STATE.work.all.filter(
      (x) => String(x.status || "").toLowerCase() === "blocked"
    );
    STATE.work.done = STATE.work.all.filter(
      (x) => String(x.status || "").toLowerCase() === "done"
    );
  }
  
  let MOVE_LOCK = false;

  async function moveTask(id, status, toPosition = null) {
    if (!CFG.workAssignBase) throw new Error("Thiếu CFG.workAssignBase");

    if (MOVE_LOCK) {
      console.warn("[moveTask] blocked by MOVE_LOCK");
      return;
    }

    const task = findTaskById(id);
    if (!task) throw new Error("Không tìm thấy task");

    const oldTask = { ...task };
    const oldStatus = String(task.status || "todo");

    MOVE_LOCK = true;

    try {
      patchTaskLocal(id, { status });
      renderAllWork();
    

      const url = `${CFG.workAssignBase}${id}/move/`;

      const resp = await http(url, {
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

      renderAllWork();
    

      refreshTimeline(true).catch(console.warn);
      refreshHome().catch(console.warn);
      setTimeout(() => refreshWorkData().catch(console.warn), 120);
    } catch (err) {
      patchTaskLocal(id, oldTask);
      renderAllWork();
    
      throw err;
    } finally {
      MOVE_LOCK = false;
    }
  }

  async function assignTaskById(id, assigneeId) {
    if (!CFG.workAssignBase) throw new Error("Thiếu CFG.workAssignBase");

    await http(`${CFG.workAssignBase}${id}/assign/`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ assignee_id: assigneeId }),
    });
  }

  async function assignTask(id) {
    const inpId = qs(`[data-assign-id="${CSS.escape(String(id))}"]`);
    const inpBy = qs(`[data-assign-by="${CSS.escape(String(id))}"]`);

    const assigneeId = (inpId?.value || "").trim();
    const assigneeBy = (inpBy?.value || "").trim();

    if (assigneeBy && CFG.workAssignBy) {
      await http(CFG.workAssignBy, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ task_id: id, q: assigneeBy }),
      });
      return;
    }

    if (!assigneeId) {
      throw new Error("Nhập assignee_id hoặc email/username");
    }

    await assignTaskById(id, assigneeId);
  }

  async function updateTask(taskId,payload){

    const pure={};

    if("title" in payload) pure.title=payload.title;
    if("description" in payload) pure.description=payload.description;
    if("priority" in payload) pure.priority=payload.priority;
    if("due_at" in payload) pure.due_at=payload.due_at;

    if(Object.keys(pure).length){

        await http(`${CFG.workUpdateBase}${taskId}/update/`,{
            method:"POST",
            headers:{"content-type":"application/json"},
            body:JSON.stringify(pure)
        });
    }

    if("assignee_id" in payload && payload.assignee_id){

        await http(`${CFG.workAssignBase}${taskId}/assign/`,{
            method:"POST",
            headers:{"content-type":"application/json"},
            body:JSON.stringify({assignee_id:payload.assignee_id})
        });
    }

    if(payload.assign_by && CFG.workAssignBy){

        await http(CFG.workAssignBy,{
            method:"POST",
            headers:{"content-type":"application/json"},
            body:JSON.stringify({
                task_id:taskId,
                q:payload.assign_by
            })
        });
    }

    await refreshWorkData();
    await refreshTimeline(true);
    await refreshHome();
  }

  async function createTaskFromUI(payloadOverride = null) {
    const payload = payloadOverride || {};

    if (!payloadOverride) {
      const title = ($("newTaskTitle")?.value || "").trim();
      const assigneeId = ($("newTaskAssignee")?.value || "").trim();
      const assigneeBy = ($("newTaskAssigneeBy")?.value || "").trim();
      const dueAt = ($("newTaskDueAt")?.value || "").trim();
      const priority = Number(($("newTaskPriority")?.value || "2").trim() || 2);

      if (!title) {
        alert("Nhập title task nha anh");
        return;
      }

      const p = scopeParams();
      payload.title = title;
      payload.priority = priority;
      payload.due_at = dueAt || null;

      if (p.get("company_id")) payload.company_id = Number(p.get("company_id"));
      if (p.get("shop_id")) payload.shop_id = Number(p.get("shop_id"));
      if (p.get("project_id")) payload.project_id = Number(p.get("project_id"));
      if (assigneeId) payload.assignee_id = Number(assigneeId);

      const created = await createTask(payload);

      try {
        const id = created?.item?.id || created?.id;
        if (id && assigneeBy && CFG.workAssignBy) {
          await http(CFG.workAssignBy, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ task_id: id, q: assigneeBy }),
          });
        }
      } catch (e) {
        console.warn(e);
      }

      if ($("newTaskTitle")) $("newTaskTitle").value = "";
      if ($("newTaskAssignee")) $("newTaskAssignee").value = "";
      if ($("newTaskAssigneeBy")) $("newTaskAssigneeBy").value = "";
      if ($("newTaskDueAt")) $("newTaskDueAt").value = "";
      if ($("newTaskPriority")) $("newTaskPriority").value = "2";
    } else {
      await createTask(payload);
    }

    STATE.work.filters.assignee = "";
    STATE.work.filters.keyword = "";
    STATE.work.filters.company = "";
    STATE.work.filters.shop = "";
    STATE.work.filters.status = "";

    if ($("filterAssigneeFinal")) $("filterAssigneeFinal").value = "";
    if ($("filterKeywordFinal")) $("filterKeywordFinal").value = "";
    if ($("filterCompanyFinal")) $("filterCompanyFinal").value = "";
    if ($("filterShopFinal")) $("filterShopFinal").value = "";
    if ($("filterStatusFinal")) $("filterStatusFinal").value = "";

    STATE.ui.workView = "board";
    localStorage.setItem("ht_work_view", "board");
    STATE.ui.boardGroupBy = "status";
    localStorage.setItem("ht_board_group_by", "status");

    await refreshWorkData();
    switchWorkView("board");
    renderWorkBoard();
    await refreshTimeline(true);
    await refreshHome();
  }
  function renderTaskSummary(task) {
    const el = $("taskSummaryList");
    if (!el) return;

    const meta = taskMetaText(task);
    const deadline = deadlineInfo(task.due_at, task.status);

    const rows = [
      ["Mã task", "#" + (task.id || "-")],
      ["Người nhận", meta.assigneeText],
      ["Công ty", meta.companyText],
      ["Shop", meta.shopText],
      ["Dự án", meta.projectText],
      ["Deadline", fmtTime(task.due_at) || "Chưa có"],
      ["Tình trạng hạn", deadline.text],
      ["Cập nhật cuối", fmtTime(task.updated_at) || "-"],
    ];

    el.innerHTML = "";

    rows.forEach(([k, v]) => {
      const div = document.createElement("div");
      div.className = "task-summary-item";
      div.innerHTML = `
        <div class="k">${escapeHtml(k)}</div>
        <div class="v">${escapeHtml(v)}</div>
      `;
      el.appendChild(div);
    });
  }

  function renderTaskActivity(task) {
    const el = $("taskActivityList");
    if (!el) return;

    const timelineItems = (STATE.raw.timeline && STATE.raw.timeline.items) || [];
    const related = timelineItems.filter((it) => {
      const objId =
        it?.doi_tuong?.id ??
        it?.entity_id ??
        it?.object_id ??
        it?.meta?.entity_id ??
        null;

      return String(objId || "") === String(task.id);
    });

    const normalized = related.map((it) => ({
      title: it.tieu_de || it.title || "Sự kiện công việc",
      desc: it.noi_dung || it.body || it.loai || "",
      time: it.thoi_gian || it.created_at || it.time,
    }));

    const fallback = [
      {
        title: "Tạo công việc",
        desc: `Task #${task.id} đã được tạo trong hệ thống.`,
        time: task.created_at,
      },
      {
        title: "Cập nhật gần nhất",
        desc: `Task đang ở trạng thái ${task.status || "todo"}.`,
        time: task.updated_at,
      },
    ];

    const finalItems = normalized.length ? normalized.slice(0, 8) : fallback;

    el.innerHTML = "";
    finalItems.forEach((x) => {
      const div = document.createElement("div");
      div.className = "task-activity-item";
      div.innerHTML = `
        <div class="t">${escapeHtml(x.title)}</div>
        <div class="d">${escapeHtml(x.desc || "Không có mô tả.")}</div>
        <div class="time">${escapeHtml(fmtTime(x.time))}</div>
      `;
      el.appendChild(div);
    });
  }

  function openTaskDrawer(task) {
    if (!task) return;

    STATE.work.selectedTaskId = task.id;

    const drawer = $("taskDrawer");
    if (!drawer) return;

    const priority = priorityInfo(task.priority);
    const deadline = deadlineInfo(task.due_at, task.status);
    const meta = taskMetaText(task);

    if ($("taskDrawerSub")) {
      $("taskDrawerSub").textContent = `Task #${task.id} • ${meta.companyText} • ${meta.shopText}`;
    }

    if ($("taskEditTitle")) $("taskEditTitle").value = task.title || "";
    if ($("taskEditDescription")) $("taskEditDescription").value = task.description || "";
    if ($("taskEditStatus")) $("taskEditStatus").value = task.status || "todo";
    if ($("taskEditPriority")) $("taskEditPriority").value = String(task.priority || 2);
    if ($("taskEditDueAt")) $("taskEditDueAt").value = toDatetimeLocal(task.due_at);
    if ($("taskEditAssigneeId")) $("taskEditAssigneeId").value = task.assignee_id || "";
    if ($("taskEditAssigneeBy")) $("taskEditAssigneeBy").value = "";
    if ($("taskEditCompanyId")) $("taskEditCompanyId").value = task.company_id || "";
    if ($("taskEditShopId")) $("taskEditShopId").value = task.shop_id || "";
    if ($("taskEditProjectId")) $("taskEditProjectId").value = task.project_id || "";

    const priorityBadge = $("taskPriorityBadge");
    if (priorityBadge) {
      priorityBadge.className = `task-badge ${priority.cls}`;
      priorityBadge.textContent = priority.text;
    }

    const inline = $("taskInlineMeta");
    if (inline) {
      inline.innerHTML = `
        <span class="task-badge ${priority.cls}">${escapeHtml(priority.text)}</span>
        <span class="task-badge ${deadline.cls}">${escapeHtml(deadline.text)}</span>
        <span class="task-badge">Người nhận: ${escapeHtml(meta.assigneeText)}</span>
        <span class="task-badge">Công ty: ${escapeHtml(meta.companyText)}</span>
        <span class="task-badge">Shop: ${escapeHtml(meta.shopText)}</span>
        <span class="task-badge">Dự án: ${escapeHtml(meta.projectText)}</span>
      `;
    }
    refreshTaskComments(task.id).catch((e) => {
      console.warn("load comments lỗi:", e);
    });
    renderTaskSummary(task);
    renderTaskActivity(task);

    drawer.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  function closeTaskDrawer() {
    const drawer = $("taskDrawer");
    if (!drawer) return;

    drawer.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  async function saveTaskDrawer() {
    const taskId = STATE.work.selectedTaskId;
    if (!taskId) throw new Error("Chưa chọn task");

    const assigneeIdRaw = ($("taskEditAssigneeId")?.value || "").trim();
    const companyIdRaw = ($("taskEditCompanyId")?.value || "").trim();
    const shopIdRaw = ($("taskEditShopId")?.value || "").trim();
    const projectIdRaw = ($("taskEditProjectId")?.value || "").trim();
    const assigneeBy = ($("taskEditAssigneeBy")?.value || "").trim();

    const payload = {
      title: ($("taskEditTitle")?.value || "").trim(),
      description: ($("taskEditDescription")?.value || "").trim(),
      status: ($("taskEditStatus")?.value || "todo").trim(),
      priority: Number(($("taskEditPriority")?.value || "2").trim() || 2),
      due_at: ($("taskEditDueAt")?.value || "").trim() || null,
      assignee_id: assigneeIdRaw ? Number(assigneeIdRaw) : null,
      company_id: companyIdRaw ? Number(companyIdRaw) : null,
      shop_id: shopIdRaw ? Number(shopIdRaw) : null,
      project_id: projectIdRaw ? Number(projectIdRaw) : null,
      assign_by: assigneeBy || undefined,
    };

    await updateTask(taskId, payload);

    const fresh = findTaskById(taskId);
    if (fresh) openTaskDrawer(fresh);
  }
  
  async function moveTaskNextStep() {
    const taskId = STATE.work.selectedTaskId;
    const task = findTaskById(taskId);

    if (!task) throw new Error("Không tìm thấy task");

    const flow = ["todo", "doing", "blocked", "done"];
    const current = String(task.status || "todo");
    const idx = flow.indexOf(current);
    const next = idx >= 0 && idx < flow.length - 1 ? flow[idx + 1] : "done";

    await moveTask(taskId, next);

    const fresh = findTaskById(taskId);
    if (fresh) openTaskDrawer(fresh);
  }

  function bindKanbanDnD(enabled) {
    qsa(".kanban-list").forEach((col) => {
      col.replaceWith(col.cloneNode(true));
    });

    if (!enabled) return;

    qsa(".kanban-list").forEach((col) => {
      col.addEventListener("dragover", (e) => {
        e.preventDefault();
        window.__HT_LAST_DROP_Y__ = e.clientY;
        col.classList.add("drag-over");
      });

      col.addEventListener("dragleave", () => {
        col.classList.remove("drag-over");
      });

      col.addEventListener("drop", async (e) => {
        e.preventDefault();
        col.classList.remove("drag-over");

        const taskId = e.dataTransfer.getData("text/plain") || STATE.dragTaskId;
        const dropType = col.dataset.dropType || "status";
        const dropKey = col.dataset.dropKey || "";

        if (!taskId) return;
        if (dropType !== "status") return;

        try {
          const toPosition = calcDropPosition(col, taskId);
          await moveTask(taskId, dropKey, toPosition);
        } catch (err) {
          alert("Drag move lỗi: " + err.message);
        }
      });
    });
}
  let REFRESH_LOCK = false;

  async function safeRefreshAll(force = false) {
    if (STATE.isRefreshing || REFRESH_LOCK) return;

    REFRESH_LOCK = true;
    STATE.isRefreshing = true;

    try {
      applyScopeUI();
      ensureWorkToolbar();
      renderCurrentShopNotice();

      await refreshControlCenter();
      await refreshTimeline(true);
      await refreshNotifications();
      await refreshHome();

      const shouldRefreshWork =
        force ||
        STATE.ui.activeTab === "work" ||
        document.visibilityState === "visible";

      if (shouldRefreshWork) {
        await refreshWorkData();
      }

      bindKanbanDnD(STATE.ui.boardGroupBy === "status");
    } catch (e) {
      console.error(e);

      const box = $("strategyList");
      if (box) {
        box.innerHTML = `
          <div class="item">
            <div class="t">UI loaded</div>
            <div class="d">Có lỗi khi gọi API: ${escapeHtml(e.message)}</div>
          </div>
        `;
      }
    } finally {
      STATE.isRefreshing = false;

      setTimeout(() => {
        REFRESH_LOCK = false;
      }, 800);
    }
  }

  function restartSSE() {
    if (!CFG.stream) return;

    try {
      if (STATE.es) STATE.es.close();
    } catch (e) {}

    STATE.es = null;

    const p = scopeParams();
    p.set("last_id", "0");

    const url = `${CFG.stream}?${p.toString()}`;
    const rt = $("rtPill");

    try {
      STATE.es = new EventSource(url, { withCredentials: true });

      STATE.es.onopen = () => {
        if (rt) rt.textContent = "realtime";
      };

      STATE.es.onerror = () => {
        if (rt) rt.textContent = "reconnect…";
      };

      const onTick = async () => {
        const now = Date.now();

        if (STATE.isRefreshing) return;
        if (now - STATE.sseCooldownAt < 5000) return;

        STATE.sseCooldownAt = now;

        try {
          await refreshTimeline(true);
          await refreshNotifications();

          // tạm thời KHÔNG auto refresh work ở SSE
          // vì dễ làm board bị nhảy ngược ngay sau khi move
          // await refreshWorkData();
        } catch (e) {
          console.warn("SSE refresh lỗi:", e);
        }

        const first = qs("#timelineList .item");
        if (first) {
          first.classList.add("flash");
          setTimeout(() => first.classList.remove("flash"), 900);
        }
      };

      STATE.es.onmessage = onTick;
      STATE.es.addEventListener("event", onTick);
    } catch (e) {
      if (rt) rt.textContent = "realtime off";
    }
  }
  function normalizeInt(v) {
    return String(v || "").trim().replace(/\D/g, "");
  }

  function openCreateTaskModal() {
    const m = $("createTaskModal");
    if (!m) return;

    $("createTaskCompanyId").value = STATE.scope.company_id || "";
    $("createTaskShopId").value = STATE.scope.shop_id || "";
    $("createTaskProjectId").value = STATE.scope.project_id || "";
    $("createTaskPriority").value = "2";
    $("createTaskError").textContent = "";
    $("createTaskOk").textContent = "";

    const parts = [];
    if (STATE.scope.company_id) parts.push("Company #" + STATE.scope.company_id);
    if (STATE.scope.shop_id) parts.push("Shop #" + STATE.scope.shop_id);
    if (STATE.scope.project_id) parts.push("Project #" + STATE.scope.project_id);

    $("createTaskContextLine").textContent = parts.length
      ? "Ngữ cảnh hiện tại: " + parts.join(" • ")
      : "Chưa khóa company/shop/project. Anh nên chọn ngữ cảnh trước khi tạo task.";

    m.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";

    setTimeout(() => {
      $("createTaskTitle")?.focus();
    }, 50);
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
    if ($("createTaskCompanyId")) $("createTaskCompanyId").value = STATE.scope.company_id || "";
    if ($("createTaskShopId")) $("createTaskShopId").value = STATE.scope.shop_id || "";
    if ($("createTaskProjectId")) $("createTaskProjectId").value = STATE.scope.project_id || "";
    if ($("createTaskPriority")) $("createTaskPriority").value = "2";
    if ($("createTaskAssigneeId")) $("createTaskAssigneeId").value = "";
    if ($("createTaskTargetType")) $("createTaskTargetType").value = "";
    if ($("createTaskTargetId")) $("createTaskTargetId").value = "";
    if ($("createTaskError")) $("createTaskError").textContent = "";
    if ($("createTaskOk")) $("createTaskOk").textContent = "";
  }

  async function submitCreateTaskModal() {
    const payload = {
      title: ($("createTaskTitle")?.value || "").trim(),
      description: ($("createTaskDescription")?.value || "").trim(),
      company_id: normalizeInt($("createTaskCompanyId")?.value || ""),
      shop_id: normalizeInt($("createTaskShopId")?.value || ""),
      project_id: normalizeInt($("createTaskProjectId")?.value || ""),
      priority: Number(normalizeInt($("createTaskPriority")?.value || "2") || 2),
      assignee_id: normalizeInt($("createTaskAssigneeId")?.value || ""),
      target_type: ($("createTaskTargetType")?.value || "").trim(),
      target_id: normalizeInt($("createTaskTargetId")?.value || ""),
    };

    if ($("createTaskError")) $("createTaskError").textContent = "";
    if ($("createTaskOk")) $("createTaskOk").textContent = "";

    if (!payload.title) {
      $("createTaskError").textContent = "Anh cần nhập tiêu đề task.";
      $("createTaskTitle")?.focus();
      return;
    }

    if (!payload.company_id && !payload.project_id && !(payload.target_type && payload.target_id)) {
      $("createTaskError").textContent = "Cần ít nhất 1 ngữ cảnh: Company ID, Project ID hoặc Target.";
      return;
    }

    if (!payload.description) delete payload.description;
    if (!payload.company_id) delete payload.company_id;
    if (!payload.shop_id) delete payload.shop_id;
    if (!payload.project_id) delete payload.project_id;
    if (!payload.assignee_id) delete payload.assignee_id;
    if (!payload.target_type) delete payload.target_type;
    if (!payload.target_id) delete payload.target_id;

    const btn = $("submitCreateTaskBtn");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Đang tạo...";
    }

    try {
      await createTaskFromUI(payload);
      $("createTaskOk").textContent = "Đã tạo task thành công.";
      setTimeout(() => {
        closeCreateTaskModal();
        resetCreateTaskModal();
      }, 450);
    } catch (err) {
      $("createTaskError").textContent = "Tạo task lỗi: " + err.message;
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Tạo task";
      }
    }
  }
    function openModal(id) {
    const m = $(id);
    if (!m) return;
    m.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  function closeModal(id) {
    const m = $(id);
    if (!m) return;
    m.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  function setCmdHints() {
    const el = $("cmdHints");
    if (!el) return;

    const hints = [
      "scope tenant",
      "scope company 1",
      "scope shop 49",
      "scope project 3",
      "work create chạy ads",
      "work assign 12 abc@gmail.com",
      "work move 12 doing",
      "mark read 12",
      "refresh",
      "theme dark",
      "board status",
      "board company",
      "board shop",
      "board assignee",
    ];

    el.innerHTML = hints.map((h) => `<span class="hint">${escapeHtml(h)}</span>`).join("");
  }

  async function runCommand(raw) {
    const out = $("cmdResult");
    const cmd = (raw || "").trim();

    if (!cmd) {
      if (out) out.textContent = "Nhập lệnh đi anh.";
      return;
    }

    const parts = cmd.split(/\s+/);
    const a = (parts[0] || "").toLowerCase();
    const b = (parts[1] || "").toLowerCase();

    if (out) out.textContent = "Đang chạy...";

    try {
      if (a === "refresh") {
        await safeRefreshAll();
        if (out) out.textContent = "Đã làm mới.";
        return;
      }

      if (a === "theme") {
        const t =
          b === "light" || b === "dark"
            ? b
            : (STATE.ui.theme === "dark" ? "light" : "dark");

        setTheme(t);
        if (out) out.textContent = "Theme: " + t;
        return;
      }

      if (a === "board") {
        if (["status", "company", "shop", "assignee"].includes(b)) {
          STATE.ui.boardGroupBy = b;
          localStorage.setItem("ht_board_group_by", STATE.ui.boardGroupBy);

          if ($("boardGroupByFinal")) {
            $("boardGroupByFinal").value = STATE.ui.boardGroupBy;
          }

          renderWorkBoard();
          bindKanbanDnD(STATE.ui.boardGroupBy === "status");

          if (out) out.textContent = "Board = " + b;
          return;
        }
      }

      if (a === "scope") {
        if (b === "tenant") {
          setScope("tenant", {
            company_id: "",
            shop_id: "",
            project_id: "",
          });
          if (out) out.textContent = "Scope = tenant";
          return;
        }

        if (b === "company") {
          setScope("company", {
            company_id: parts[2] || "",
            shop_id: "",
            project_id: "",
          });
          if (out) out.textContent = "Scope = company";
          return;
        }

        if (b === "shop") {
          setScope("shop", {
            shop_id: parts[2] || "",
            company_id: "",
            project_id: "",
          });
          if (out) out.textContent = "Scope = shop";
          return;
        }

        if (b === "project") {
          setScope("project", {
            project_id: parts[2] || "",
            company_id: "",
            shop_id: "",
          });
          if (out) out.textContent = "Scope = project";
          return;
        }
      }

      if (a === "work" && b === "create") {
        const title = parts.slice(2).join(" ").trim();
        if (!title) {
          throw new Error("Usage: work create <title>");
        }

        const p = scopeParams();
        const payload = {
          title: title,
          priority: Number($("quickPriorityFinal")?.value || 2),
          due_at: ($("quickDeadlineFinal")?.value || "").trim() || null,
        };

        if (p.get("company_id")) payload.company_id = Number(p.get("company_id"));
        if (p.get("shop_id")) payload.shop_id = Number(p.get("shop_id"));
        if (p.get("project_id")) payload.project_id = Number(p.get("project_id"));

        await createTask(payload);
        await refreshWorkData();

        if (out) out.textContent = "Đã tạo: " + title;
        return;
      }

      if (a === "work" && b === "assign") {
        const taskId = parts[2];
        const who = parts.slice(3).join(" ").trim();

        if (!taskId || !who) {
          throw new Error("Usage: work assign <task_id> <email/username>");
        }

        if (CFG.workAssignBy) {
          await http(CFG.workAssignBy, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ task_id: taskId, q: who }),
          });
        } else {
          await assignTaskById(taskId, who);
        }

        await refreshWorkData();

        if (out) out.textContent = `Đã giao việc ${taskId} → ${who}`;
        return;
      }

      if (a === "work" && b === "move") {
        const taskId = parts[2];
        const status = (parts[3] || "").trim();

        if (!taskId || !status) {
          throw new Error("Usage: work move <task_id> <status>");
        }

        await moveTask(taskId, status);

        if (out) out.textContent = `Đã chuyển ${taskId} → ${status}`;
        return;
      }

      if (a === "mark" && b === "read") {
        const id = (parts[2] || "").trim();
        if (!id) {
          throw new Error("Usage: mark read <id>");
        }

        await http(`${CFG.notifications}${id}/read/`, { method: "POST" });
        await refreshNotifications();

        if (out) out.textContent = "Đã đọc thông báo: " + id;
        return;
      }

      if (CFG.commandCenter) {
        const resp = await http(CFG.commandCenter, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ command: cmd }),
        });

        if (out) {
          out.textContent =
            typeof resp === "string" ? resp : JSON.stringify(resp, null, 2);
        }

        await safeRefreshAll();
        return;
      }

      if (out) out.textContent = "Lệnh chưa hỗ trợ.";
    } catch (e) {
      if (out) out.textContent = "Error: " + (e?.message || e);
    }
  }

  function bindEvents() {
    if (STATE.eventsBound) return;
    STATE.eventsBound = true;

    qsa("#scopeChips .chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        const s = btn.dataset.scope;
        if (s === "tenant") {
          setScope("tenant", { company_id: "", shop_id: "", project_id: "" });
        } else {
          setScope(s);
        }
      });
    });
    $("btnNewTask")?.addEventListener("click", openCreateTaskModal);
    $("closeCreateTaskBtn")?.addEventListener("click", closeCreateTaskModal);
    $("createTaskBackdrop")?.addEventListener("click", closeCreateTaskModal);
    $("resetCreateTaskBtn")?.addEventListener("click", resetCreateTaskModal);
    $("submitCreateTaskBtn")?.addEventListener("click", submitCreateTaskModal);
    $("themeToggle")?.addEventListener("click", () => {
      setTheme(STATE.ui.theme === "dark" ? "light" : "dark");
    });

    $("helpBtn")?.addEventListener("click", () => openModal("helpModal"));

    $("cmdBtn")?.addEventListener("click", () => {
      openModal("cmdModal");
      setCmdHints();
      setTimeout(() => $("cmdInput")?.focus(), 50);
    });

    $("bbCmd")?.addEventListener("click", () => {
      openModal("cmdModal");
      setCmdHints();
      setTimeout(() => $("cmdInput")?.focus(), 50);
    });

    qsa("[data-close='1']").forEach((x) => {
      x.addEventListener("click", () => {
        closeModal("cmdModal");
        closeModal("helpModal");
      });
    });

    $("cmdRun")?.addEventListener("click", () => {
      runCommand($("cmdInput")?.value || "");
    });

    $("cmdInput")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        runCommand(e.target.value);
      }

      if (e.key === "Escape") closeModal("cmdModal");
    });

    $("loadMoreTimeline")?.addEventListener("click", () => refreshTimeline(false));
    $("btnRefreshKernel")?.addEventListener("click", refreshHome);

    $("btnRawToggle")?.addEventListener("click", () => {
      const rawBox = $("rawBox");
      const rawHint = $("rawHint");
      if (!rawBox) return;

      const isHidden = rawBox.style.display === "none" || rawBox.style.display === "";
      rawBox.style.display = isHidden ? "block" : "none";
      if (rawHint) rawHint.style.display = isHidden ? "none" : "block";
      renderRawJson();
    });

    qsa(".raw-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        qsa(".raw-tab").forEach((x) => x.classList.remove("active"));
        btn.classList.add("active");
        STATE.raw.active = btn.dataset.raw || "home";
        renderRawJson();
      });
    });
    
    qsa(".work-view-tab").forEach((btn) => {
      btn.addEventListener("click", async () => {
        STATE.ui.activeTab = "work";
        switchWorkView(btn.dataset.view || "list");

        if (!STATE.work.all.length) {
          await refreshWorkData();
        }

        if ((btn.dataset.view || "list") === "board") {
          renderWorkBoard();
        }
      });
    });


    $("btnCancelTask")?.addEventListener("click", () => {
      if ($("workCreateBox")) $("workCreateBox").style.display = "none";
    });

    $("btnCreateTask")?.addEventListener("click", createTaskFromUI);

    $("btnRefreshWork")?.addEventListener("click", async () => {
      await refreshWorkData();
    });

    document.addEventListener("input", (e) => {
      if (e.target?.id === "filterAssigneeFinal") {
        STATE.work.filters.assignee = e.target.value || "";
        renderAllWork();
        return;
      }

      if (e.target?.id === "filterKeywordFinal") {
        STATE.work.filters.keyword = e.target.value || "";
        renderAllWork();
        return;
      }

      if (e.target?.id === "filterCompanyFinal") {
        STATE.work.filters.company = e.target.value || "";
        renderAllWork();
        return;
      }

      if (e.target?.id === "filterShopFinal") {
        STATE.work.filters.shop = e.target.value || "";
        renderAllWork();
        return;
      }
    });

    document.addEventListener("change", (e) => {
      if (e.target?.id === "filterStatusFinal") {
        STATE.work.filters.status = e.target.value || "";
        renderAllWork();
        return;
      }

      if (e.target?.id === "boardGroupByFinal") {
        STATE.ui.boardGroupBy = e.target.value || "status";
        localStorage.setItem("ht_board_group_by", STATE.ui.boardGroupBy);
        renderWorkBoard();
        bindKanbanDnD(STATE.ui.boardGroupBy === "status");
        return;
      }
    });

    document.addEventListener("click", async (e) => {
      const quickLinkBtn = e.target.closest(".os-quick-link-btn");
      if (quickLinkBtn) {
        const url = quickLinkBtn.dataset.url || "";
        const targetId = quickLinkBtn.dataset.target || "";

        if (url) {
          window.location.href = url;
          return;
        }

        if (targetId) {
          scrollToOSSection(targetId);
          return;
        }
      }

      const clearFilter = e.target.closest("#btnClearFilterFinal");
      if (clearFilter) {
        STATE.work.filters.assignee = "";
        STATE.work.filters.keyword = "";
        STATE.work.filters.company = "";
        STATE.work.filters.shop = "";
        STATE.work.filters.status = "";

        if ($("filterAssigneeFinal")) $("filterAssigneeFinal").value = "";
        if ($("filterKeywordFinal")) $("filterKeywordFinal").value = "";
        if ($("filterCompanyFinal")) $("filterCompanyFinal").value = "";
        if ($("filterShopFinal")) $("filterShopFinal").value = "";
        if ($("filterStatusFinal")) $("filterStatusFinal").value = "";


        renderAllWork();
        return;
      }

      const reloadBoard = e.target.closest("#btnReloadBoardFinal");
      if (reloadBoard) {
        await refreshWorkData();
        return;
      }

      const shopQuick = e.target.closest(".shop-nav-final");
      if (shopQuick) {
        const shopId = shopQuick.dataset.shopId || "";
        setScope("shop", { shop_id: shopId, company_id: "", project_id: "" });
        return;
      }

      const openTaskBtn = e.target.closest("[data-open-task]");
      if (openTaskBtn) {
        const taskId = openTaskBtn.dataset.openTask;
        const task = findTaskById(taskId);
        if (task) openTaskDrawer(task);
        return;
      }

      const assignBtn = e.target.closest(".assignBtn");
      if (assignBtn) {
        const id = assignBtn.dataset.id;
        assignBtn.textContent = "…";

        try {
          await assignTask(id);
          await refreshWorkData();
        } catch (err) {
          alert("Assign lỗi: " + err.message);
        } finally {
          assignBtn.textContent = "Assign";
        }
        return;
      }

      const moveBtn = e.target.closest(".moveBtn");
      if (moveBtn) {
        const id = moveBtn.dataset.id;
        const sel = qs(`.statusSel[data-id="${CSS.escape(String(id))}"]`);
        const status = sel ? sel.value : "";

        moveBtn.textContent = "…";

        try {
          await moveTask(id, status);
        } catch (err) {
          alert("Move lỗi: " + err.message);
        } finally {
          moveBtn.textContent = "Move";
        }
        return;
      }

      const kbMoveBtn = e.target.closest(".kb-move-btn");
      if (kbMoveBtn) {
        const id = kbMoveBtn.dataset.id;
        const status = qs(`.kb-status[data-id="${CSS.escape(String(id))}"]`)?.value || "";
        const priority = Number(qs(`.kb-priority[data-id="${CSS.escape(String(id))}"]`)?.value || 2);

        kbMoveBtn.textContent = "…";

        try {
          const task = findTaskById(id);
          const currentPriority = Number(task?.priority || 2);

          if (priority !== currentPriority) {
            await updateTask(id, { priority });
            await moveTask(id, status, 1);
          }

          await moveTask(id, status);
        } catch (err) {
          alert("Move lỗi: " + err.message);
        } finally {
          kbMoveBtn.textContent = "Move";
        }
        return;
      }

      const markReadBtn = e.target.closest(".mark-read-btn");
      if (markReadBtn) {
        const id = markReadBtn.dataset.id;
        markReadBtn.textContent = "…";

        try {
          await http(`${CFG.notifications}${id}/read/`, { method: "POST" });
          await refreshNotifications();
        } catch (err) {
          alert("Read lỗi: " + err.message);
        } finally {
          markReadBtn.textContent = "Đánh dấu đã đọc";
        }
        return;
      }

      const createBtn = e.target.closest(".kb-col-create-btn");
      if (createBtn) {
        const groupType = createBtn.dataset.groupType || "status";
        const groupKey = createBtn.dataset.groupKey || "";
        const input = qs(
          `.kb-col-create-title[data-group-type="${CSS.escape(groupType)}"][data-group-key="${CSS.escape(groupKey)}"]`
        );

        try {
          await quickCreateByGroup(groupType, groupKey, input);
        } catch (err) {
          alert("Quick create lỗi: " + err.message);
        }
        return;
      }

      const editOpenBtn = e.target.closest(".kb-edit-open-btn");
      if (editOpenBtn) {
        const id = editOpenBtn.dataset.id;
        const box = qs(`[data-edit-box="${CSS.escape(String(id))}"]`);
        if (!box) return;

        const visible = box.style.display !== "none";
        qsa(".kb-inline-edit").forEach((x) => (x.style.display = "none"));
        box.style.display = visible ? "none" : "block";
        return;
      }

      const editCancelBtn = e.target.closest(".kb-cancel-btn");
      if (editCancelBtn) {
        const id = editCancelBtn.dataset.id;
        const box = qs(`[data-edit-box="${CSS.escape(String(id))}"]`);
        if (box) box.style.display = "none";
        return;
      }

      const editSaveBtn = e.target.closest(".kb-save-btn");
      if (editSaveBtn) {
        const id = editSaveBtn.dataset.id;
        const title = qs(`.kb-edit-title[data-id="${CSS.escape(String(id))}"]`)?.value || "";
        const description = qs(`.kb-edit-desc[data-id="${CSS.escape(String(id))}"]`)?.value || "";
        const due_at = qs(`.kb-edit-deadline[data-id="${CSS.escape(String(id))}"]`)?.value || "";
        const priority = Number(qs(`.kb-priority[data-id="${CSS.escape(String(id))}"]`)?.value || 2);

        editSaveBtn.textContent = "…";

        try {
          await updateTask(id, {
            title: title.trim(),
            description: description.trim(),
            due_at: due_at || null,
            priority,
          });
        } catch (err) {
          alert("Lưu task lỗi: " + err.message);
        } finally {
          editSaveBtn.textContent = "Lưu";
        }
        return;
      }
    });

    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        openModal("cmdModal");
        setCmdHints();
        setTimeout(() => $("cmdInput")?.focus(), 50);
      }

      if ((e.ctrlKey || e.metaKey) && e.key === "/") {
        e.preventDefault();
        setTheme(STATE.ui.theme === "dark" ? "light" : "dark");
      }

      if (!e.ctrlKey && !e.metaKey && e.key.toLowerCase() === "r") {
        safeRefreshAll();
      }

      if (e.key === "Escape") {
        closeTaskDrawer();
        closeModal("cmdModal");
        closeModal("helpModal");
      }
    });

    qsa(".bb-item").forEach((b) => {
      b.addEventListener("click", () => {
        qsa(".bb-item").forEach((x) => x.classList.remove("active"));
        b.classList.add("active");

        const tab = b.dataset.tab || "";
        STATE.ui.activeTab = tab || "home";

        if (tab === "timeline") $("timelineList")?.scrollIntoView({ behavior: "smooth", block: "start" });
        if (tab === "alerts") $("notifList")?.scrollIntoView({ behavior: "smooth", block: "start" });
        if (tab === "work") $("workPanel")?.scrollIntoView({ behavior: "smooth", block: "start" });
        if (tab === "home") window.scrollTo({ top: 0, behavior: "smooth" });

        if (tab === "command") {
          openModal("cmdModal");
          setCmdHints();
          setTimeout(() => $("cmdInput")?.focus(), 50);
        }
      });
    });

    $("q")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        openModal("cmdModal");
        setCmdHints();

        const inp = $("cmdInput");
        if (inp) inp.value = (e.target.value || "").trim();

        setTimeout(() => $("cmdInput")?.focus(), 50);
      }
    });

    $("btnCloseTaskDrawer")?.addEventListener("click", closeTaskDrawer);

    qsa("[data-drawer-close='1']").forEach((x) => {
      x.addEventListener("click", closeTaskDrawer);
    });

    $("btnSaveTaskDrawer")?.addEventListener("click", async () => {
      const btn = $("btnSaveTaskDrawer");
      if (btn) btn.textContent = "Đang lưu...";

      try {
        await saveTaskDrawer();
      } catch (err) {
        alert("Lưu task lỗi: " + err.message);
      } finally {
        if (btn) btn.textContent = "Lưu thay đổi";
      }
    });

    $("btnMoveNextTaskDrawer")?.addEventListener("click", async () => {
      const btn = $("btnMoveNextTaskDrawer");
      if (btn) btn.textContent = "Đang xử lý...";

      try {
        await moveTaskNextStep();
      } catch (err) {
        alert("Move task lỗi: " + err.message);
      } finally {
        if (btn) btn.textContent = "Đẩy sang bước tiếp";
      }
    });

    document.addEventListener("keydown", async (e) => {
      if (e.target?.classList?.contains("kb-col-create-title") && e.key === "Enter") {
        e.preventDefault();

        try {
          await quickCreateByGroup(
            e.target.dataset.groupType || "status",
            e.target.dataset.groupKey || "",
            e.target
          );
        } catch (err) {
          alert("Quick create lỗi: " + err.message);
        }
      }
    });

    document.addEventListener("dragstart", (e) => {
      const card = e.target.closest(".kcard");
      if (!card) return;
      STATE.dragTaskId = card.dataset.id || null;
      card.classList.add("dragging");
    });

    document.addEventListener("dragend", (e) => {
      const card = e.target.closest(".kcard");
      if (card) card.classList.remove("dragging");
      STATE.dragTaskId = null;
      qsa(".kanban-list").forEach((x) => x.classList.remove("drag-over"));
    });

    $("btnSubmitTaskComment")?.addEventListener("click", async (e) => {
      e.preventDefault();

      const btn = $("btnSubmitTaskComment");
      if (btn) btn.textContent = "Đang gửi...";

      try {
        await submitTaskComment();
      } catch (err) {
        alert("Gửi comment lỗi: " + err.message);
      } finally {
        if (btn) btn.textContent = "Gửi comment";
      }
    });

    $("taskCommentInput")?.addEventListener("keydown", async (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        try {
          await submitTaskComment();
        } catch (err) {
          alert("Gửi comment lỗi: " + err.message);
        }
      }
    });
    window.addEventListener("scroll", () => {
      syncOSQuickLinksByScroll();
    }, { passive: true });
  }

  function ensureStyles() {
    if ($("htFinalStylePatch")) return;

    const style = document.createElement("style");
    style.id = "htFinalStylePatch";
    style.textContent = `
      #workBoardWrap{
        display:block;
        width:100%;
        overflow-x:auto;
        overflow-y:hidden;
        padding-bottom:6px;
      }
      .priority-critical{
        color:#ef4444;
      }

      .priority-warning{
        color:#f59e0b;
      }

      .priority-info{
        color:#38bdf8;
      }

      #workBoard{
        display:grid !important;
        grid-template-columns:repeat(4, minmax(280px, 1fr)) !important;
        gap:14px;
        align-items:start;
        min-width:1200px;
      }

      .kcard.dragging{
        opacity:.45;
        transform:scale(.98);
      }

      .kanban-col{
        width:auto !important;
        min-width:280px;
        max-width:none !important;
        border:1px solid rgba(255,255,255,.08);
        border-radius:16px;
        background:rgba(255,255,255,.03);
        overflow:hidden;
        display:flex;
        flex-direction:column;
        min-height:420px;
      }

      .kanban-col-group{
        width:auto !important;
        min-width:280px;
        max-width:none !important;
      }

      .kanban-head{
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:8px;
        padding:12px;
        border-bottom:1px solid rgba(255,255,255,.06);
        font-weight:800;
      }

      .kanban-list{
        min-height:260px;
        padding:10px;
        border-radius:14px;
      }

      .kanban-list.drag-over{
        border:1px dashed rgba(110,168,254,.55);
        background:rgba(110,168,254,.08);
        border-radius:14px;
      }
      
      .kanban-empty{
        padding:14px;
        border:1px dashed rgba(255,255,255,.10);
        border-radius:12px;
        color:var(--muted);
        font-size:13px;
        text-align:center;
      }

      .kcard.v12{
        border:1px solid rgba(255,255,255,.07);
        border-radius:14px;
        padding:12px;
        background:rgba(255,255,255,.03);
        margin-bottom:10px;
        cursor:grab;
      }

      .kcard .ktitle{
        font-weight:850;
        margin-bottom:8px;
        line-height:1.35;
      }

      .kcard .kmeta{
        display:flex;
        gap:8px;
        flex-wrap:wrap;
        font-size:12px;
        color:var(--muted);
        margin-bottom:6px;
      }

      .kcard .kdesc{
        font-size:12px;
        line-height:1.5;
        margin:8px 0;
        color:var(--text);
        opacity:.92;
      }

      .kcard .kact{
        display:flex;
        gap:8px;
        align-items:center;
        margin-top:10px;
        flex-wrap:wrap;
      }

      .kb-inline-edit textarea.input{
        width:100%;
        resize:vertical;
      }

      .kb-quick-create .input,
      .kb-inline-edit .input,
      #workToolbarFinal .input{
        border-radius:10px;
        border:1px solid rgba(255,255,255,.08);
        background:rgba(255,255,255,.03);
        color:inherit;
        padding:10px 12px;
        outline:none;
      }

      @media (max-width: 1200px){
        #workBoard{
          grid-template-columns:repeat(2, minmax(280px, 1fr)) !important;
          min-width:760px;
        }
      }

      @media (max-width: 768px){
        #workBoard{
          grid-template-columns:1fr !important;
          min-width:100%;
        }

        #workBoardWrap{
          overflow-x:hidden;
        }

        .kanban-col{
          min-width:100%;
        }
      }
    `;
    document.head.appendChild(style);
  }

  async function boot() {
    ensureStyles();
    setTheme(STATE.ui.theme);
    applyScopeUI();
    renderCurrentShopNotice();
    ensureWorkToolbar();
    ensureOSQuickLinks();
    bindEvents();
    switchWorkView(STATE.ui.workView);

    const currentTenantId = String(window.HT_TENANT_ID || "").trim();
    if (currentTenantId) {
      localStorage.setItem("ht_tenant_id", currentTenantId);
    }

    if (!localStorage.getItem("ht_board_group_by")) {
      STATE.ui.boardGroupBy = "status";
      localStorage.setItem("ht_board_group_by", "status");
    } else {
      STATE.ui.boardGroupBy = localStorage.getItem("ht_board_group_by") || "status";
    }

    await safeRefreshAll(true);

    if ($("boardGroupByFinal")) {
      $("boardGroupByFinal").value = STATE.ui.boardGroupBy;
    }

    setTimeout(() => {
      restartSSE();
    }, 1500);
  }
  async function quickCreateTasks(text, status="todo"){
    const resp = await http("/api/v1/os/work/quick-create/",{
      method:"POST",
      headers:{"content-type":"application/json"},
      body:JSON.stringify({
        text,
        status
      })
    });

    if(resp?.items){
      resp.items.forEach(x=>{
        STATE.work.all.push(x);
      });

      renderAllWork();
    }

    return resp;
  }

  async function quickCreateTask(title, status) {
    const resp = await http("/api/v1/os/work/create/", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        title,
        status,
      }),
    });

    if (resp?.item) {
      STATE.work.all.push(resp.item);
      renderAllWork();
    }

    return resp;
  }

  function bindQuickCreateInputs() {
    qsa(".kanban-add-input").forEach((input) => {
      input.addEventListener("keydown", async (e) => {
        if (e.key !== "Enter") return;

        const title = input.value.trim();
        const status = input.dataset.status;

        if (!title) return;

        try {
          await quickCreateTask(title, status);
          input.value = "";
        } catch (err) {
          console.error("create task lỗi", err);
        }
      });
    });
  }

  function renderTaskComments(items) {
    const box = $("taskCommentsList");
    if (!box) return;

    const arr = Array.isArray(items) ? items : [];

    if (!arr.length) {
      box.innerHTML = `
        <div class="item">
          <div class="t">Chưa có comment</div>
          <div class="d">Viết comment đầu tiên cho công việc này.</div>
        </div>
      `;
      return;
    }

    box.innerHTML = "";

    arr.forEach((c) => {
      const actor =
        c.actor_name ||
        c.actor_email ||
        c.user_name ||
        c.user_email ||
        "User";

      const body =
        c.body ||
        c.content ||
        "";

      const div = document.createElement("div");
      div.className = "task-comment-item";
      div.innerHTML = `
        <div class="t">${escapeHtml(actor)}</div>
        <div class="time">${escapeHtml(fmtTime(c.created_at))}</div>
        <div class="d">${escapeHtml(body)}</div>
      `;
      box.appendChild(div);
    });
  }
  async function submitTaskComment() {
    const taskId = STATE.work.selectedTaskId;
    if (!taskId) throw new Error("Chưa chọn task");

    const inp = $("taskCommentInput");
    const body = (inp?.value || "").trim();

    if (!body) {
      alert("Nhập comment đã anh");
      return;
    }

    if (!CFG.workCommentsBase) {
      throw new Error("Thiếu CFG.workCommentsBase");
    }

    await http(`${CFG.workCommentsBase}${taskId}/comments/`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ body }),
    });

    if (inp) inp.value = "";

    await refreshTaskComments(taskId);
    await refreshTimeline(true);
  }
  function renderContractRadar(data){

    const timelineBox = $("contractTimelineBox");
    if(!timelineBox) return;

    let box = $("contractRadarBox");

    if(!box){
      box=document.createElement("div");
      box.id="contractRadarBox";
      box.className="card";

      box.innerHTML=`
      <div class="card-h">
        <div>
          <div class="card-t">Contract Radar</div>
          <div class="muted">Theo dõi rủi ro hợp đồng theo Shop</div>
        </div>
      </div>
      <div class="card-b" id="contractRadarList"></div>
      `;

      timelineBox.parentNode.insertBefore(box,timelineBox.nextSibling);
    }

    const list=$("contractRadarList");
    if(!list) return;

    const shops=data?.shops||[];

    if(!shops.length){
      list.innerHTML=`<div class="muted">Không có rủi ro hợp đồng</div>`;
      return;
    }

    list.innerHTML="";

    shops.forEach(shop=>{
        const div=document.createElement("div");
        div.className="item";

        let html=`<div class="t">Shop ${shop.shop_id}</div>`;

        shop.contracts.forEach(c=>{
            html+=`<div class="d"><b>${c.contract_code}</b></div>`;

            c.items.forEach(i=>{
                html+=`
                <div class="row">
                  <span>${i.title}</span>
                  <span class="priority-${i.priority}">${i.priority}</span>
                </div>`;
            });

        });

        div.innerHTML=html;
        list.appendChild(div);
    });

  }
  function renderFounderDashboard(data) {
    const timelineBox = $("timelineList")?.closest(".card");
    if (!timelineBox) return;

    let box = $("founderDashboardBox");
    if (!box) {
      box = document.createElement("div");
      box.id = "founderDashboardBox";
      box.className = "card";
      box.style.marginTop = "12px";
      box.style.marginBottom = "12px";
      box.innerHTML = `
        <div class="card-h">
          <div>
            <div class="card-t">Founder Dashboard</div>
            <div class="muted">Tổng quan tài chính, backlog và mức độ rủi ro vận hành</div>
          </div>
        </div>
        <div class="card-b">
          <div id="founderSummaryCards" class="fd-cards"></div>
          <div id="founderFinanceBox" style="margin-top:12px;"></div>
          <div id="founderRiskBox" style="margin-top:12px;"></div>
        </div>
      `;
      timelineBox.parentNode.insertBefore(box, timelineBox);
    }
    box.style.gridColumn = "1 / -1";
    box.style.width = "100%";

    const cardsEl = $("founderSummaryCards");
    const financeEl = $("founderFinanceBox");
    const riskEl = $("founderRiskBox");
    if (!cardsEl || !financeEl || !riskEl) return;

    const blocks = data?.blocks || {};
    const cards = Array.isArray(blocks.summary_cards) ? blocks.summary_cards : [];
    const finance = blocks.finance || {};
    const risk = blocks.risk || {};

    cardsEl.innerHTML = cards.map((x) => `
      <div class="fd-card">
        <div class="fd-k">${escapeHtml(x.label || "")}</div>
        <div class="fd-v">${escapeHtml(x.value || "0")} ${escapeHtml(x.unit || "")}</div>
      </div>
    `).join("");

    financeEl.innerHTML = `
      <div class="item">
        <div class="t">Tài chính vận hành</div>
        <div class="row">
          <span>Công nợ quá hạn: <b>${escapeHtml(finance.receivable_overdue_total || "0")} đ</b></span>
          <span>Công nợ 7 ngày tới: <b>${escapeHtml(finance.receivable_due_soon_total || "0")} đ</b></span>
        </div>
        <div class="row" style="margin-top:6px;">
          <span>Payout quá hạn: <b>${escapeHtml(finance.payout_overdue_total || "0")} đ</b></span>
          <span>Payout 7 ngày tới: <b>${escapeHtml(finance.payout_due_soon_total || "0")} đ</b></span>
        </div>
      </div>
    `;

    riskEl.innerHTML = `
      <div class="item">
        <div class="t">Mức độ rủi ro tổng</div>
        <div class="row">
          <span class="priority-${escapeHtml(risk.level || "info")}">Level: ${escapeHtml(risk.level || "info")}</span>
          <span>Score: <b>${escapeHtml(risk.score || 0)}</b></span>
          <span>Backlog quá hạn: <b>${escapeHtml(risk.backlog_overdue || 0)}</b></span>
          <span>Task gấp: <b>${escapeHtml(risk.backlog_urgent || 0)}</b></span>
        </div>
      </div>
    `;
  }
  function renderShopRiskRadar(data) {
    const founderBox = $("founderDashboardBox");
    if (!founderBox) return;

    let box = $("shopRiskRadarBox");
    if (!box) {
      box = document.createElement("div");
      box.id = "shopRiskRadarBox";
      box.className = "card";
      box.style.marginTop = "12px";
      box.style.marginBottom = "12px";
      box.style.gridColumn = "1 / -1";
      box.style.width = "100%";
      box.innerHTML = `
        <div class="card-h">
          <div>
            <div class="card-t">Shop Risk Ranking</div>
            <div class="muted">Xếp hạng shop theo mức độ rủi ro vận hành</div>
          </div>
        </div>
        <div class="card-b">
          <div id="shopRiskRadarSummary" class="muted" style="margin-bottom:10px;"></div>
          <div id="shopRiskRadarList"></div>
        </div>
      `;
      founderBox.parentNode.insertBefore(box, founderBox.nextSibling);
    }

    const summaryEl = $("shopRiskRadarSummary");
    const listEl = $("shopRiskRadarList");
    if (!summaryEl || !listEl) return;

    const headline = data?.headline || {};
    const items = Array.isArray(data?.items) ? data.items : [];

    summaryEl.innerHTML = `
      Tổng shop có rủi ro: <b>${headline.shop_risk_total || 0}</b> •
      Critical: <b>${headline.shop_risk_critical || 0}</b> •
      Warning: <b>${headline.shop_risk_warning || 0}</b> •
      Info: <b>${headline.shop_risk_info || 0}</b>
    `;

    if (!items.length) {
      listEl.innerHTML = `
        <div class="item">
          <div class="t">Chưa có shop rủi ro</div>
          <div class="d">Hiện chưa có shop nào vượt ngưỡng rủi ro.</div>
        </div>
      `;
      return;
    }

    listEl.innerHTML = "";

    items.forEach((x, idx) => {
      const div = document.createElement("div");
      div.className = "item";
      div.innerHTML = `
        <div class="t">
          #${idx + 1} • ${escapeHtml(x.shop_name || ("Shop #" + (x.shop_id || "")))}
          <span class="priority-${escapeHtml(x.level || "info")}" style="margin-left:8px;">${escapeHtml(x.level || "info")}</span>
        </div>
        <div class="row" style="margin-top:6px;">
          <span>Score: <b>${escapeHtml(x.score || 0)}</b></span>
          <span>Payment overdue: <b>${escapeHtml(x.payment_overdue || 0)}</b></span>
          <span>Milestone overdue: <b>${escapeHtml(x.milestone_overdue || 0)}</b></span>
        </div>
        <div class="row" style="margin-top:6px;">
          <span>Payout overdue: <b>${escapeHtml(x.booking_payout_overdue || 0)}</b></span>
          <span>Air thiếu link: <b>${escapeHtml(x.booking_air_missing || 0)}</b></span>
          <span>Task overdue: <b>${escapeHtml(x.work_overdue || 0)}</b></span>
          <span>Task gấp: <b>${escapeHtml(x.work_urgent || 0)}</b></span>
        </div>
      `;
      listEl.appendChild(div);
    });
  }
  function renderCashflowRadar(data) {

    const founderBox = $("founderDashboardBox");
    if (!founderBox) return;

    let box = $("cashflowRadarBox");

    if (!box) {

      box = document.createElement("div");
      box.id = "cashflowRadarBox";
      box.className = "card";
      box.style.gridColumn = "1 / -1";
      box.style.marginTop = "12px";

      box.innerHTML = `
        <div class="card-h">
          <div>
            <div class="card-t">Cashflow Radar</div>
            <div class="muted">Dự báo dòng tiền 30 ngày</div>
          </div>
        </div>
        <div class="card-b">
          <div id="cashflowRadarList"></div>
        </div>
      `;

      founderBox.parentNode.insertBefore(box, founderBox.nextSibling);
    }

    const list = $("cashflowRadarList");
    if (!list) return;

    const items = Array.isArray(data?.items) ? data.items : [];

    list.innerHTML = items.map(x => `
      <div class="item">
        <div class="t">${escapeHtml(x.label || "")}</div>
        <div class="row">
          <b>${escapeHtml(x.value || "0")}</b>
        </div>
      </div>
    `).join("");

  }
  function renderRevenuePrediction(data){

    const founderBox = $("founderDashboardBox");
    if(!founderBox) return;

    let box = $("revenuePredictionBox");

    if(!box){

      box = document.createElement("div");
      box.id = "revenuePredictionBox";
      box.className = "card";
      box.style.gridColumn = "1 / -1";
      box.style.marginTop = "12px";

      box.innerHTML = `
        <div class="card-h">
          <div>
            <div class="card-t">Revenue Prediction</div>
            <div class="muted">Dự đoán doanh thu 30 ngày</div>
          </div>
        </div>
        <div class="card-b">
          <div id="revenuePredictionList"></div>
        </div>
      `;

      founderBox.parentNode.insertBefore(box, founderBox.nextSibling);
    }

    const list = $("revenuePredictionList");
    if(!list) return;

    const items = Array.isArray(data?.items) ? data.items : [];

    list.innerHTML = items.map(x => `
      <div class="item">
        <div class="t">${escapeHtml(x.label || "")}</div>
        <div class="row">
          <b>${escapeHtml(x.value || "0")}</b>
        </div>
      </div>
    `).join("");

  }
  function renderAIDecisions(data) {
    const revenueBox = $("revenuePredictionBox");
    if (!revenueBox) return;

    let box = $("aiDecisionBox");
    if (!box) {
      box = document.createElement("div");
      box.id = "aiDecisionBox";
      box.className = "card";
      box.style.gridColumn = "1 / -1";
      box.style.width = "100%";
      box.style.marginTop = "12px";
      box.innerHTML = `
        <div class="card-h">
          <div>
            <div class="card-t">AI Decisions</div>
            <div class="muted">Gợi ý hành động ưu tiên cho founder / operator</div>
          </div>
        </div>
        <div class="card-b">
          <div id="aiDecisionSummary" class="muted" style="margin-bottom:10px;"></div>
          <div id="aiDecisionList"></div>
        </div>
      `;
      revenueBox.parentNode.insertBefore(box, revenueBox.nextSibling);
    }

    const summaryEl = $("aiDecisionSummary");
    const listEl = $("aiDecisionList");
    if (!summaryEl || !listEl) return;

    const headline = data?.headline || {};
    const items = Array.isArray(data?.items) ? data.items : [];

    summaryEl.innerHTML = `
      Tổng đề xuất: <b>${headline.ai_decision_total || 0}</b> •
      Critical: <b>${headline.ai_decision_critical || 0}</b> •
      Warning: <b>${headline.ai_decision_warning || 0}</b>
    `;

    if (!items.length) {
      listEl.innerHTML = `
        <div class="item">
          <div class="t">Chưa có quyết định ưu tiên</div>
          <div class="d">Hiện chưa có tín hiệu rủi ro đủ mạnh để sinh đề xuất hành động.</div>
        </div>
      `;
      return;
    }

    listEl.innerHTML = "";

    items.forEach((x) => {
      const div = document.createElement("div");
      div.className = "item";
      div.innerHTML = `
        <div class="t">
          ${escapeHtml(x.title || "AI Decision")}
          <span class="priority-${escapeHtml(x.priority || "info")}" style="margin-left:8px;">${escapeHtml(x.priority || "info")}</span>
        </div>
        <div class="d" style="margin-top:6px;">${escapeHtml(x.summary || "")}</div>
        <div class="row" style="margin-top:8px;">
          <span><b>Action:</b> ${escapeHtml(x.action || "")}</span>
        </div>
      `;
      listEl.appendChild(div);
    });
  }
  function renderContractHealthScore(data) {
    const aiBox = $("aiDecisionBox");
    if (!aiBox) return;

    let box = $("contractHealthScoreBox");
    if (!box) {
      box = document.createElement("div");
      box.id = "contractHealthScoreBox";
      box.className = "card";
      box.style.gridColumn = "1 / -1";
      box.style.width = "100%";
      box.style.marginTop = "12px";
      box.innerHTML = `
        <div class="card-h">
          <div>
            <div class="card-t">Contract Health Score</div>
            <div class="muted">Chấm điểm sức khỏe từng hợp đồng</div>
          </div>
        </div>
        <div class="card-b">
          <div id="contractHealthSummary" class="muted" style="margin-bottom:10px;"></div>
          <div id="contractHealthList"></div>
        </div>
      `;
      aiBox.parentNode.insertBefore(box, aiBox.nextSibling);
    }

    const summaryEl = $("contractHealthSummary");
    const listEl = $("contractHealthList");
    if (!summaryEl || !listEl) return;

    const headline = data?.headline || {};
    const items = Array.isArray(data?.items) ? data.items : [];

    summaryEl.innerHTML = `
      Tổng hợp đồng: <b>${headline.contract_health_total || 0}</b> •
      Good: <b>${headline.contract_health_good || 0}</b> •
      Warning: <b>${headline.contract_health_warning || 0}</b> •
      Critical: <b>${headline.contract_health_critical || 0}</b>
    `;

    if (!items.length) {
      listEl.innerHTML = `
        <div class="item">
          <div class="t">Chưa có dữ liệu sức khỏe hợp đồng</div>
          <div class="d">Hiện chưa có hợp đồng nào trong phạm vi đang theo dõi.</div>
        </div>
      `;
      return;
    }

    listEl.innerHTML = "";

    items.forEach((x, idx) => {
      const levelClass =
        x.level === "good" ? "priority-info" :
        x.level === "warning" ? "priority-warning" :
        "priority-critical";

      const issues = Array.isArray(x.issues) ? x.issues : [];

      const div = document.createElement("div");
      div.className = "item";
      div.innerHTML = `
        <div class="t">
          #${idx + 1} • ${escapeHtml(x.contract_code || "")} • ${escapeHtml(x.contract_name || "")}
          <span class="${levelClass}" style="margin-left:8px;">${escapeHtml(x.level || "critical")}</span>
        </div>
        <div class="row" style="margin-top:6px;">
          <span>Score: <b>${escapeHtml(x.score || 0)}</b></span>
          <span>Type: <b>${escapeHtml(x.contract_type || "")}</b></span>
          <span>Payment overdue: <b>${escapeHtml(x.payments_overdue || 0)}</b></span>
          <span>Milestone overdue: <b>${escapeHtml(x.milestones_overdue || 0)}</b></span>
        </div>
        <div class="row" style="margin-top:6px;">
          <span>Payout overdue: <b>${escapeHtml(x.booking_payout_overdue || 0)}</b></span>
          <span>Air thiếu link: <b>${escapeHtml(x.booking_air_missing || 0)}</b></span>
          <span>Task overdue: <b>${escapeHtml(x.contract_work_overdue || 0)}</b></span>
        </div>
        ${issues.length ? `<div class="d" style="margin-top:8px;">${escapeHtml(issues.join(" • "))}</div>` : ""}
      `;
      listEl.appendChild(div);
    });
  }
  function renderMissionControl(data) {
    const root = document.querySelector(".grid") || document.body;

    let box = $("missionControlBox");

    if (!box) {
      box = document.createElement("div");
      box.id = "missionControlBox";
      box.className = "card";
      box.style.gridColumn = "1 / -1";

      box.innerHTML = `
        <div class="card-h">
          <div>
            <div class="card-t">Mission Control</div>
            <div class="muted">Agency trạng thái tổng thể</div>
          </div>
        </div>
        <div class="card-b">
          <div id="missionStatus"></div>
          <div id="missionRisks"></div>
          <div id="missionActions"></div>
        </div>
      `;

      root.prepend(box);
    }

    const status = data?.headline?.status || "good";

    const statusEl = $("missionStatus");

    statusEl.innerHTML = `
      <div class="row">
        <span>Status:</span>
        <b class="priority-${status}">${status.toUpperCase()}</b>
      </div>
    `;

    const risks = data?.risks || [];
    const actions = data?.actions || [];

    const risksEl = $("missionRisks");
    const actionsEl = $("missionActions");

    risksEl.innerHTML = `
      <h4>Top Risks</h4>
    `;

    risks.forEach((r) => {
      risksEl.innerHTML += `
        <div class="item">
          <div class="t">${escapeHtml(r.title)}</div>
          <div class="d">${escapeHtml(r.summary)}</div>
        </div>
      `;
    });

    actionsEl.innerHTML = `
      <h4>Top Actions</h4>
    `;

    actions.forEach((a) => {
      actionsEl.innerHTML += `
        <div class="item">
          <div class="t">${escapeHtml(a.title)}</div>
          <div class="d">${escapeHtml(a.action)}</div>
        </div>
      `;
    });
  }
  function renderAgencyHealth(data) {

    const mission = $("missionControlBox");
    if (!mission) return;

    let box = $("agencyHealthBox");

    if (!box) {

      box = document.createElement("div");
      box.id = "agencyHealthBox";
      box.className = "card";
      box.style.gridColumn = "1 / -1";

      box.innerHTML = `
        <div class="card-h">
          <div>
            <div class="card-t">Agency Health Score</div>
            <div class="muted">Chỉ số vận hành toàn agency</div>
          </div>
        </div>

        <div class="card-b">

          <div id="agencyHealthMain"></div>

          <div id="agencyHealthDetail"></div>

        </div>
      `;

      mission.parentNode.insertBefore(box, mission.nextSibling);
    }

    const score = data?.score || 0;
    const blocks = data?.blocks || {};

    const main = $("agencyHealthMain");

    main.innerHTML = `
      <div style="font-size:32px;font-weight:700;">
        ${score} / 100
      </div>
    `;

    const detail = $("agencyHealthDetail");

    detail.innerHTML = `
      <div class="row">
        <span>Finance</span>
        <b>${blocks.finance || 0}</b>
      </div>

      <div class="row">
        <span>Delivery</span>
        <b>${blocks.delivery || 0}</b>
      </div>

      <div class="row">
        <span>Contracts</span>
        <b>${blocks.contracts || 0}</b>
      </div>

      <div class="row">
        <span>Operations</span>
        <b>${blocks.operations || 0}</b>
      </div>
    `;
  }
  function renderShopBrain(data){

    const root = document.querySelector(".grid") || document.body

    let box = $("shopBrainBox")

    if(!box){

      box = document.createElement("div")
      box.id = "shopBrainBox"
      box.className = "card"
      box.style.gridColumn = "1 / -1"

      box.innerHTML = `
        <div class="card-h">
          <div>
            <div class="card-t">Shop Daily Mission</div>
            <div class="muted">Việc cần làm hôm nay</div>
          </div>
        </div>

        <div class="card-b">

          <div id="shopMission"></div>

          <div id="shopRisk"></div>

          <div id="shopGrowth"></div>

        </div>
      `

      root.prepend(box)
    }

    const mission = data?.daily_mission || []
    const risks = data?.risks || []
    const growth = data?.growth || []

    const missionEl = $("shopMission")
    const riskEl = $("shopRisk")
    const growthEl = $("shopGrowth")

    missionEl.innerHTML = `<h4>Hôm nay nên làm</h4>`
    mission.forEach(x=>{
      missionEl.innerHTML += `
        <div class="item">
          <div class="t">${escapeHtml(x.title)}</div>
          <div class="d">${escapeHtml(x.summary)}</div>
        </div>
      `
    })

    riskEl.innerHTML = `<h4>Rủi ro</h4>`
    risks.forEach(x=>{
      riskEl.innerHTML += `
        <div class="item">
          <div class="t">${escapeHtml(x.title)}</div>
          <div class="d">${escapeHtml(x.summary)}</div>
        </div>
      `
    })

    growthEl.innerHTML = `<h4>Gợi ý tăng trưởng</h4>`
    growth.forEach(x=>{
      growthEl.innerHTML += `
        <div class="item">
          <div class="t">${escapeHtml(x.title)}</div>
          <div class="d">${escapeHtml(x.summary)}</div>
        </div>
      `
    })
  }
  function renderProductRadar(data) {
    const shopBrainBox = $("shopBrainBox");
    if (!shopBrainBox) return;

    let box = $("productRadarBox");
    if (!box) {
      box = document.createElement("div");
      box.id = "productRadarBox";
      box.className = "card";
      box.style.gridColumn = "1 / -1";
      box.innerHTML = `
        <div class="card-h">
          <div>
            <div class="card-t">Product Radar</div>
            <div class="muted">Theo dõi SKU bán tốt, lỗ, ROAS thấp và sắp hết hàng</div>
          </div>
        </div>
        <div class="card-b">
          <div id="productRadarWrap"></div>
        </div>
      `;
      shopBrainBox.parentNode.insertBefore(box, shopBrainBox.nextSibling);
    }

    const wrap = $("productRadarWrap");
    if (!wrap) return;

    const blocks = data?.blocks || {};
    const topSku = Array.isArray(blocks.top_sku) ? blocks.top_sku : [];
    const lowRoas = Array.isArray(blocks.low_roas) ? blocks.low_roas : [];
    const losingSku = Array.isArray(blocks.losing_sku) ? blocks.losing_sku : [];
    const lowStock = Array.isArray(blocks.low_stock) ? blocks.low_stock : [];

    function rowHtml(x, extra) {
      return `
        <div class="item">
          <div class="t">${escapeHtml(x.sku || "")} • ${escapeHtml(x.name || "")}</div>
          <div class="row">
            ${extra}
          </div>
        </div>
      `;
    }

    wrap.innerHTML = `
      <div class="fd-cards">
        <div class="fd-card">
          <div class="fd-k">Top SKU</div>
          <div>
            ${topSku.length ? topSku.map(x => rowHtml(
              x,
              `<span>Revenue: <b>${escapeHtml(x.revenue || "0")}</b></span>
              <span>Units: <b>${escapeHtml(x.units_sold || 0)}</b></span>`
            )).join("") : `<div class="muted">Chưa có dữ liệu</div>`}
          </div>
        </div>

        <div class="fd-card">
          <div class="fd-k">ROAS thấp</div>
          <div>
            ${lowRoas.length ? lowRoas.map(x => rowHtml(
              x,
              `<span>ROAS: <b>${escapeHtml(x.roas_estimate || "0")}</b></span>
              <span>Ads: <b>${escapeHtml(x.ads_spend || "0")}</b></span>`
            )).join("") : `<div class="muted">Chưa có dữ liệu</div>`}
          </div>
        </div>

        <div class="fd-card">
          <div class="fd-k">SKU lỗ</div>
          <div>
            ${losingSku.length ? losingSku.map(x => rowHtml(
              x,
              `<span>Profit: <b>${escapeHtml(x.profit_estimate || "0")}</b></span>`
            )).join("") : `<div class="muted">Chưa có SKU lỗ</div>`}
          </div>
        </div>

        <div class="fd-card">
          <div class="fd-k">Sắp hết hàng</div>
          <div>
            ${lowStock.length ? lowStock.map(x => rowHtml(
              x,
              `<span>Stock: <b>${escapeHtml(x.stock || 0)}</b></span>`
            )).join("") : `<div class="muted">Tồn kho đang ổn</div>`}
          </div>
        </div>
      </div>
    `;
  }
  function renderShopServicesOverview(data) {
      const productRadarBox = $("productRadarBox");
      if (!productRadarBox) return;

      let box = $("shopServicesOverviewBox");
      if (!box) {
        box = document.createElement("div");
        box.id = "shopServicesOverviewBox";
        box.className = "card";
        box.style.gridColumn = "1 / -1";
        box.innerHTML = `
          <div class="card-h">
            <div>
              <div class="card-t">Shop Services Overview</div>
              <div class="muted">Các dịch vụ shop đang sử dụng và trạng thái hiện tại</div>
            </div>
          </div>
          <div class="card-b">
            <div id="shopServicesOverviewSummary" class="muted" style="margin-bottom:10px;"></div>
            <div id="shopServicesOverviewList"></div>
          </div>
        `;
        productRadarBox.parentNode.insertBefore(box, productRadarBox.nextSibling);
      }

      const summaryEl = $("shopServicesOverviewSummary");
      const listEl = $("shopServicesOverviewList");
      if (!summaryEl || !listEl) return;

      const headline = data?.headline || {};
      const items = Array.isArray(data?.items) ? data.items : [];

      summaryEl.innerHTML = `
        Tổng dịch vụ: <b>${headline.shop_services_total || 0}</b> •
        Active: <b>${headline.shop_services_active || 0}</b> •
        Paused: <b>${headline.shop_services_paused || 0}</b> •
        Ended: <b>${headline.shop_services_ended || 0}</b>
      `;

      if (!items.length) {
        listEl.innerHTML = `
          <div class="item">
            <div class="t">Chưa có dịch vụ nào</div>
            <div class="d">Hiện shop chưa được gắn dịch vụ nào trong hệ thống.</div>
          </div>
        `;
        return;
      }

      listEl.innerHTML = "";

      items.forEach((x) => {
        const div = document.createElement("div");
        div.className = "item";
        div.innerHTML = `
          <div class="t">
            ${escapeHtml(x.service_name || x.service_code || "")}
            <span class="priority-${x.status === "active" ? "info" : x.status === "paused" ? "warning" : "critical"}" style="margin-left:8px;">
              ${escapeHtml(x.status || "")}
            </span>
          </div>
          <div class="row" style="margin-top:6px;">
            <span>Shop: <b>${escapeHtml(x.shop_name || "")}</b></span>
            <span>Owner: <b>${escapeHtml(x.owner_name || "-")}</b></span>
          </div>
          <div class="row" style="margin-top:6px;">
            <span>Contract: <b>${escapeHtml(x.contract_code || "-")}</b></span>
            <span>Bắt đầu: <b>${escapeHtml(x.start_date || "-")}</b></span>
            <span>Kết thúc: <b>${escapeHtml(x.end_date || "-")}</b></span>
          </div>
          ${x.note ? `<div class="d" style="margin-top:8px;">${escapeHtml(x.note)}</div>` : ""}
        `;
        listEl.appendChild(div);
      });
    }
    function renderShopServiceTimeline(data) {
    const overviewBox = $("shopServicesOverviewBox");
    if (!overviewBox) return;

    let box = $("shopServiceTimelineBox");
    if (!box) {
      box = document.createElement("div");
      box.id = "shopServiceTimelineBox";
      box.className = "card";
      box.style.gridColumn = "1 / -1";
      box.innerHTML = `
        <div class="card-h">
          <div>
            <div class="card-t">Shop Service Timeline</div>
            <div class="muted">Lịch booking, milestone, payment và vòng đời dịch vụ</div>
          </div>
        </div>
        <div class="card-b">
          <div id="shopServiceTimelineSummary" class="muted" style="margin-bottom:10px;"></div>
          <div id="shopServiceTimelineList"></div>
        </div>
      `;
      overviewBox.parentNode.insertBefore(box, overviewBox.nextSibling);
    }

    const summaryEl = $("shopServiceTimelineSummary");
    const listEl = $("shopServiceTimelineList");
    if (!summaryEl || !listEl) return;

    const headline = data?.headline || {};
    const items = Array.isArray(data?.items) ? data.items : [];

    summaryEl.innerHTML = `
      Tổng mốc: <b>${headline.shop_service_timeline_total || 0}</b> •
      Critical: <b>${headline.shop_service_timeline_critical || 0}</b> •
      Warning: <b>${headline.shop_service_timeline_warning || 0}</b> •
      Info: <b>${headline.shop_service_timeline_info || 0}</b>
    `;

    if (!items.length) {
      listEl.innerHTML = `
        <div class="item">
          <div class="t">Chưa có timeline dịch vụ</div>
          <div class="d">Hiện chưa có lịch booking / milestone / payment gần tới.</div>
        </div>
      `;
      return;
    }

    listEl.innerHTML = "";

    items.forEach((x) => {
      const div = document.createElement("div");
      div.className = "item";
      div.innerHTML = `
        <div class="t">
          ${escapeHtml(x.title || "")}
          <span class="priority-${escapeHtml(x.priority || "info")}" style="margin-left:8px;">
            ${escapeHtml(x.priority || "info")}
          </span>
        </div>
        <div class="d" style="margin-top:6px;">${escapeHtml(x.summary || "")}</div>
        <div class="row" style="margin-top:6px;">
          <span>Loại: <b>${escapeHtml(x.kind || "")}</b></span>
          <span>Hợp đồng: <b>${escapeHtml(x.contract_code || "-")}</b></span>
          <span>Thời gian: <b>${escapeHtml(fmtTime(x.event_at) || "-")}</b></span>
        </div>
      `;
      listEl.appendChild(div);
    });
  }
  function renderShopCommandCenter(data){

    const root = $("missionControlBox");
    if(!root) return;

    let box = $("shopCommandCenterBox");

    if(!box){
      box = document.createElement("div");
      box.id = "shopCommandCenterBox";
      box.className = "card";
      box.style.gridColumn = "1 / -1";

      box.innerHTML = `
        <div class="card-h">
          <div>
            <div class="card-t">Shop Command Center</div>
            <div class="muted">Những việc quan trọng nhất hôm nay</div>
          </div>
        </div>
        <div class="card-b">
          <div id="shopCommandList"></div>
        </div>
      `;

      root.parentNode.insertBefore(box, root);
    }

    const list = $("shopCommandList");
    if(!list) return;

    const missions = data?.missions || [];

    if(!missions.length){
      list.innerHTML = `<div class="muted">Không có cảnh báo quan trọng</div>`;
      return;
    }

    list.innerHTML = missions.map(x => `
      <div class="item">
        <div class="t">
          ${escapeHtml(x.title)}
          <span class="priority-${x.priority}" style="margin-left:8px">
            ${x.priority}
          </span>
        </div>
        <div class="d">${escapeHtml(x.summary)}</div>
      </div>
    `).join("");
  }
  function renderShopAIActions(data) {
    const commandBox = $("shopCommandCenterBox");
    if (!commandBox) return;

    let box = $("shopAIActionsBox");
    if (!box) {
      box = document.createElement("div");
      box.id = "shopAIActionsBox";
      box.className = "card";
      box.style.gridColumn = "1 / -1";
      box.innerHTML = `
        <div class="card-h">
          <div>
            <div class="card-t">AI Action Engine</div>
            <div class="muted">Đề xuất hành động hằng ngày cho chủ shop</div>
          </div>
        </div>
        <div class="card-b">
          <div id="shopAIActionsSummary" class="muted" style="margin-bottom:10px;"></div>
          <div id="shopAIActionsList"></div>
        </div>
      `;
      commandBox.parentNode.insertBefore(box, commandBox.nextSibling);
    }

    const summaryEl = $("shopAIActionsSummary");
    const listEl = $("shopAIActionsList");
    if (!summaryEl || !listEl) return;

    const headline = data?.headline || {};
    const items = Array.isArray(data?.items) ? data.items : [];

    summaryEl.innerHTML = `
      Tổng action: <b>${headline.shop_ai_actions_total || 0}</b> •
      Critical: <b>${headline.shop_ai_actions_critical || 0}</b> •
      Warning: <b>${headline.shop_ai_actions_warning || 0}</b> •
      Info: <b>${headline.shop_ai_actions_info || 0}</b>
    `;

    if (!items.length) {
      listEl.innerHTML = `
        <div class="item">
          <div class="t">Chưa có action đề xuất</div>
          <div class="d">Hiện chưa có tín hiệu đủ mạnh để sinh hành động mới.</div>
        </div>
      `;
      return;
    }

    listEl.innerHTML = "";

    items.forEach((x) => {
      const div = document.createElement("div");
      div.className = "item";
      div.innerHTML = `
        <div class="t">
          ${escapeHtml(x.title || "Action")}
          <span class="priority-${escapeHtml(x.priority || "info")}" style="margin-left:8px;">
            ${escapeHtml(x.priority || "info")}
          </span>
        </div>
        <div class="d" style="margin-top:6px;">${escapeHtml(x.summary || "")}</div>
        <div class="row" style="margin-top:8px;">
          <span><b>Gợi ý:</b> ${escapeHtml(x.action || "")}</span>
        </div>
      `;
      listEl.appendChild(div);
    });
  }
  function renderShopMissionDigest(data) {
    const commandBox = $("shopCommandCenterBox");
    const root = commandBox ? commandBox.parentNode : (document.querySelector(".grid") || document.body);

    let box = $("shopMissionDigestBox");
    if (!box) {
      box = document.createElement("div");
      box.id = "shopMissionDigestBox";
      box.className = "card";
      box.style.gridColumn = "1 / -1";
      box.innerHTML = `
        <div class="card-h">
          <div>
            <div class="card-t">Hôm nay cần làm gì</div>
            <div class="muted">3 việc quan trọng nhất cho chủ shop</div>
          </div>
        </div>
        <div class="card-b">
          <div id="shopMissionDigestSummary" class="muted" style="margin-bottom:10px;"></div>
          <div id="shopMissionDigestList"></div>
        </div>
      `;
      if (commandBox) {
        root.insertBefore(box, commandBox);
      } else {
        root.prepend(box);
      }
    }

    const summaryEl = $("shopMissionDigestSummary");
    const listEl = $("shopMissionDigestList");
    if (!summaryEl || !listEl) return;

    const headline = data?.headline || {};
    const items = Array.isArray(data?.items) ? data.items : [];

    summaryEl.innerHTML = `
      Tổng mission: <b>${headline.shop_mission_digest_total || 0}</b> •
      Critical: <b>${headline.shop_mission_digest_critical || 0}</b> •
      Warning: <b>${headline.shop_mission_digest_warning || 0}</b>
    `;

    if (!items.length) {
      listEl.innerHTML = `
        <div class="item">
          <div class="t">Hôm nay khá ổn</div>
          <div class="d">Hiện chưa có việc gấp nổi bật cần ưu tiên ngay.</div>
        </div>
      `;
      return;
    }

    listEl.innerHTML = "";

    items.forEach((x, idx) => {
      const div = document.createElement("div");
      div.className = "item";
      div.innerHTML = `
        <div class="t">
          #${idx + 1} • ${escapeHtml(x.title || "Mission")}
          <span class="priority-${escapeHtml(x.priority || "info")}" style="margin-left:8px;">
            ${escapeHtml(x.priority || "info")}
          </span>
        </div>
        <div class="d" style="margin-top:6px;">${escapeHtml(x.summary || "")}</div>
      `;
      listEl.appendChild(div);
    });
  }
  function ensureOSQuickLinks() {
    const root = document.querySelector(".grid") || document.body;
    if (!root) return;

    let box = $("osQuickLinksBox");
    if (!box) {
      box = document.createElement("div");
      box.id = "osQuickLinksBox";
      box.className = "card";
      box.style.gridColumn = "1 / -1";
      box.innerHTML = `
        <div class="card-b" style="padding:10px 12px;">
          <div id="osQuickLinksWrap" style="display:flex; gap:8px; flex-wrap:wrap;"></div>
        </div>
      `;
    }

    const anchor =
      $("shopKPIStripBox") ||
      $("shopMissionDigestBox") ||
      $("shopCommandCenterBox") ||
      root.firstElementChild ||
      null;

    if (anchor) {
      if (box !== anchor.previousElementSibling) {
        root.insertBefore(box, anchor);
      }
    } else if (!box.parentNode) {
      root.prepend(box);
    }

    const wrap = $("osQuickLinksWrap");
    if (!wrap) return;

    const links = [
      { label: "OS", url: "/os" },
      { label: "Khu làm việc", url: "/work" },
      { label: "KPI shop", target: "shopKPIStripBox" },
      { label: "Radar SKU", target: "skuRadarBox" },
      { label: "Hôm nay cần làm", target: "shopMissionDigestBox" },
      { label: "AI hành động", target: "shopAIActionsBox" },
      { label: "Dịch vụ shop", target: "shopServicesOverviewBox" },
      { label: "Timeline dịch vụ", target: "shopServiceTimelineBox" },
      { label: "Thông báo", target: "notifList" },
    ];

    wrap.innerHTML = links.map((x) => {
      if (x.url) {
        return `
          <button
            type="button"
            class="btn mini os-quick-link-btn"
            data-url="${escapeHtml(x.url)}"
          >
            ${escapeHtml(x.label)}
          </button>
        `;
      }

      return `
        <button
          type="button"
          class="btn mini os-quick-link-btn"
          data-target="${escapeHtml(x.target)}"
        >
          ${escapeHtml(x.label)}
        </button>
      `;
    }).join("");
  }

  function getOSQuickLinkSections() {
    return [
      { btnTarget: "shopKPIStripBox", sectionId: "shopKPIStripBox" },
      { btnTarget: "skuRadarBox", sectionId: "skuRadarBox" },
      { btnTarget: "shopMissionDigestBox", sectionId: "shopMissionDigestBox" },
      { btnTarget: "shopAIActionsBox", sectionId: "shopAIActionsBox" },
      { btnTarget: "shopServicesOverviewBox", sectionId: "shopServicesOverviewBox" },
      { btnTarget: "shopServiceTimelineBox", sectionId: "shopServiceTimelineBox" },
      { btnTarget: "notifList", sectionId: "notifList" },
    ];
  }

  function setActiveOSQuickLink(targetId) {
    qsa(".os-quick-link-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.target === targetId);
    });
  }
  function syncOSQuickLinksByScroll() {
    const sections = getOSQuickLinkSections();
    let activeId = "";

    for (const item of sections) {
      const el = $(item.sectionId);
      if (!el) continue;

      const rect = el.getBoundingClientRect();

      if (rect.top <= 140 && rect.bottom >= 140) {
        activeId = item.btnTarget;
        break;
      }
    }

    if (activeId) {
      setActiveOSQuickLink(activeId);
    }
  }

  function scrollToOSSection(targetId) {
    const el = document.getElementById(targetId);
    if (!el) {
      alert("Mục này chưa có dữ liệu hoặc chưa render xong.");
      return;
    }

    setActiveOSQuickLink(targetId);

    el.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }
  function renderShopKPIStrip(data) {
    const missionBox = $("shopMissionDigestBox");
    const root = missionBox ? missionBox.parentNode : (document.querySelector(".grid") || document.body);

    let box = $("shopKPIStripBox");
    if (!box) {
      box = document.createElement("div");
      box.id = "shopKPIStripBox";
      box.className = "card";
      box.style.gridColumn = "1 / -1";
      box.innerHTML = `
        <div class="card-b">
          <div id="shopKPIStripWrap" class="fd-cards"></div>
        </div>
      `;
      if (missionBox) {
        root.insertBefore(box, missionBox);
      } else {
        root.prepend(box);
      }
    }

    const wrap = $("shopKPIStripWrap");
    if (!wrap) return;

    const items = Array.isArray(data?.items) ? data.items : [];

    if (!items.length) {
      wrap.innerHTML = `<div class="muted">Chưa có KPI shop.</div>`;
      return;
    }

    wrap.innerHTML = items.map((x) => `
      <div class="fd-card">
        <div class="fd-k">${escapeHtml(x.label || "")}</div>
        <div class="fd-v">${escapeHtml(x.value || "0")} ${escapeHtml(x.unit || "")}</div>
      </div>
    `).join("");
  }
  function renderSKURadar(data) {

    const kpiBox = $("shopKPIStripBox");
    const root = kpiBox ? kpiBox.parentNode : (document.querySelector(".grid") || document.body);

    let box = $("skuRadarBox");

    if (!box) {

      box = document.createElement("div");
      box.id = "skuRadarBox";
      box.className = "card";
      box.style.gridColumn = "1 / -1";

      box.innerHTML = `
        <div class="card-h">
          <div>
            <div class="card-t">Radar SKU</div>
            <div class="muted">Theo dõi SKU bán tốt, ROAS thấp và SKU đang lỗ</div>
          </div>
        </div>

        <div class="card-b">
          <div id="skuRadarWrap" class="fd-cards"></div>
        </div>
      `;

      if (kpiBox) {
        root.insertBefore(box, kpiBox.nextSibling);
      } else {
        root.prepend(box);
      }
    }

    const wrap = $("skuRadarWrap");
    if (!wrap) return;

    const blocks = data?.blocks || {};

    const topSelling = blocks.top_selling || [];
    const lowRoas = blocks.low_roas || [];
    const losingSku = blocks.losing_sku || [];
    const lowStock = blocks.low_stock || [];

    function itemHtml(x, extra) {

      return `
        <div class="item">
          <div class="t">${escapeHtml(x.sku || "")} • ${escapeHtml(x.name || "")}</div>
          <div class="row">${extra}</div>
        </div>
      `;
    }

    wrap.innerHTML = `

      <div class="fd-card">
        <div class="fd-k">SKU bán tốt</div>
        ${topSelling.length ? topSelling.map(x => itemHtml(
          x,
          `<span>Doanh thu: <b>${x.revenue}</b></span>
          <span>SL: <b>${x.units_sold}</b></span>`
        )).join("") : `<div class="muted">Chưa có dữ liệu</div>`}
      </div>

      <div class="fd-card">
        <div class="fd-k">ROAS thấp</div>
        ${lowRoas.length ? lowRoas.map(x => itemHtml(
          x,
          `<span>ROAS: <b>${x.roas_estimate}</b></span>`
        )).join("") : `<div class="muted">Chưa có dữ liệu</div>`}
      </div>

      <div class="fd-card">
        <div class="fd-k">SKU đang lỗ</div>
        ${losingSku.length ? losingSku.map(x => itemHtml(
          x,
          `<span>Lợi nhuận: <b>${x.profit_estimate}</b></span>`
        )).join("") : `<div class="muted">Chưa có SKU lỗ</div>`}
      </div>

      <div class="fd-card">
        <div class="fd-k">Sắp hết hàng</div>
        ${lowStock.length ? lowStock.map(x => itemHtml(
          x,
          `<span>Tồn kho: <b>${x.stock}</b></span>`
        )).join("") : `<div class="muted">Tồn kho ổn</div>`}
      </div>

    `;
  }
  async function submitSales() {
    const sku = (document.getElementById("skuInput")?.value || "").trim();
    const units = document.getElementById("unitsSoldInput")?.value || 0;
    const revenue = document.getElementById("revenueInput")?.value || 0;
    const ads = document.getElementById("adsInput")?.value || 0;
    const result = document.getElementById("salesResult");
    const shopId = getCurrentShopId();

    if (!shopId) {
      alert("Anh chọn shop trước nha, rồi mới nhập doanh số SKU được.");
      return;
    }

    if (!sku) {
      alert("Anh nhập mã SKU trước nha");
      return;
    }

    try {
      const res = await fetch("/api/v1/os/products/daily-stats/upsert/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({
          shop_id: parseInt(shopId, 10),
          sku: sku,
          units_sold: parseInt(units || 0, 10),
          revenue: parseFloat(revenue || 0),
          ads_spend: parseFloat(ads || 0),
        }),
      });

      const data = await res.json();

      if (!res.ok || !data.ok) {
        result.innerHTML = `<span style="color:#f87171;">Lưu dữ liệu lỗi: ${data.message || "Không xác định"}</span>`;
        return;
      }

      result.innerHTML =
        `Đã ghi nhận cho shop <b>#${shopId}</b> • ` +
        `ROAS: <b>${data.item?.roas_estimate ?? "-"}</b> • ` +
        `Lợi nhuận ước tính: <b>${data.item?.profit_estimate ?? "-"}</b>`;

      if (window.safeRefreshAll) {
        setTimeout(() => window.safeRefreshAll(true), 300);
      }
    } catch (e) {
      result.innerHTML = `<span style="color:#f87171;">Gửi dữ liệu lỗi, vui lòng thử lại</span>`;
      console.error("submitSales error:", e);
    }
  }
  async function submitSales() {
    const sku = (document.getElementById("skuInput")?.value || "").trim();
    const units = document.getElementById("unitsSoldInput")?.value || 0;
    const revenue = document.getElementById("revenueInput")?.value || 0;
    const ads = document.getElementById("adsInput")?.value || 0;
    const result = document.getElementById("salesResult");
    const shopId = getCurrentShopId();

    if (!shopId) {
      alert("Anh chọn shop trước nha, rồi mới nhập doanh số SKU được.");
      return;
    }

    if (!sku) {
      alert("Anh nhập mã SKU trước nha");
      return;
    }

    try {
      const headers = {
        "Content-Type": "application/json"
      };

      const tenantId =
        String(window.HT_TENANT_ID || "").trim() ||
        String(localStorage.getItem("ht_tenant_id") || "").trim();

      if (tenantId) headers["X-Tenant-Id"] = tenantId;

      const csrf = getCookie("csrftoken");
      if (csrf) headers["X-CSRFToken"] = csrf;

      const res = await fetch("/api/v1/os/products/daily-stats/upsert/", {
        method: "POST",
        headers,
        credentials: "include",
        body: JSON.stringify({
          shop_id: parseInt(shopId, 10),
          sku: sku,
          units_sold: parseInt(units || 0, 10),
          revenue: parseFloat(revenue || 0),
          ads_spend: parseFloat(ads || 0)
        })
      });

      const data = await res.json();

      if (!res.ok || !data.ok) {
        result.innerHTML = `<span style="color:#f87171;">Lưu dữ liệu lỗi: ${escapeHtml(data.message || "Không xác định")}</span>`;
        return;
      }

      result.innerHTML =
        `Đã ghi nhận cho shop <b>#${escapeHtml(shopId)}</b> • ` +
        `ROAS: <b>${escapeHtml(data.item.roas_estimate)}</b> • ` +
        `Lợi nhuận ước tính: <b>${escapeHtml(data.item.profit_estimate)}</b>`;

      if (window.safeRefreshAll) {
        setTimeout(() => window.safeRefreshAll(true), 300);
      }
    } catch (e) {
      result.innerHTML = `<span style="color:#f87171;">Gửi dữ liệu lỗi, vui lòng thử lại</span>`;
    }
  }
  function updateHeroStats(data){
    try{
      const headline = data?.headline || {};
      const blocks = data?.blocks || {};

      const shops =
        headline.shops_total ??
        headline.total_shops ??
        (Array.isArray(blocks.shops_health) ? blocks.shops_health.length : 0) ??
        0;

      const tasks =
        headline.work_open ??
        headline.open_tasks ??
        headline.tasks_open ??
        headline.contract_work_open ??
        0;

      const revenue =
        headline.revenue_today ??
        headline.today_revenue ??
        headline.gmv_today ??
        0;

      const alerts =
        headline.alerts ??
        headline.alert_total ??
        headline.notifications_unread ??
        headline.risk_alerts ??
        headline.contract_work_urgent ??
        0;

      const s1 = document.getElementById("heroShops");
      const s2 = document.getElementById("heroTasks");
      const s3 = document.getElementById("heroRevenue");
      const s4 = document.getElementById("heroAlerts");

      if (s1) s1.textContent = String(shops || 0);
      if (s2) s2.textContent = String(tasks || 0);
      if (s3) s3.textContent = Number(revenue || 0).toLocaleString("vi-VN");
      if (s4) s4.textContent = String(alerts || 0);
    } catch (e) {
      console.warn("updateHeroStats error:", e);
    }
  }
  document.addEventListener("DOMContentLoaded", function () {
    const wrap = document.getElementById("osQuickCreate");
    const btn = document.getElementById("osQuickCreateBtn");
    const menu = document.getElementById("osQuickCreateMenu");

    if (!wrap || !btn || !menu) return;

    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      menu.hidden = !menu.hidden;
    });

    document.addEventListener("click", function (e) {
      if (!wrap.contains(e.target)) {
        menu.hidden = true;
      }
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        menu.hidden = true;
      }
    });
  });
window.safeRefreshAll = safeRefreshAll;
window.htRefreshWork = refreshWorkData;
window.htFindTask = findTaskById;
window.htOpenTaskDrawer = openTaskDrawer;
window.htMoveTask = moveTask;
window.htPatchTaskLocal = patchTaskLocal;
window.htStateWork = () => STATE.work;

boot();
})();