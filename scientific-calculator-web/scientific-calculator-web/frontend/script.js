(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const exprEl = $("#expr");
  const prevEl = $("#prev");
  const errEl = $("#error");
  const keysEl = $("#keys");
  const histEl = $("#history");
  const emptyHistEl = $("#emptyHist");
  const modeBtn = $("#modeBtn");
  const memInd = $("#memInd");
  const refDialog = $("#refDialog");
  const refBody = $("#refBody");

  // ---------- small storage helper (works even if storage is blocked) ----------
  const store = {
    get(key, fallback) {
      try {
        const v = localStorage.getItem(key);
        return v === null ? fallback : v;
      } catch { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem(key, value); } catch { /* ignore */ }
    },
  };

  // ---------- state ----------
  let clientId = store.get("clientId", "");
  if (!clientId) {
    clientId = (window.crypto && crypto.randomUUID)
      ? crypto.randomUUID()
      : Date.now().toString(36) + Math.random().toString(36).slice(2);
    store.set("clientId", clientId);
  }
  let angle = store.get("angle", "DEG") === "RAD" ? "RAD" : "DEG";
  let ans = Number(store.get("ans", "0")) || 0;
  let memory = Number(store.get("memory", "0")) || 0;

  // ---------- API ----------
  async function api(path, options = {}) {
    const res = await fetch(path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-Client-Id": clientId,
        ...(options.headers || {}),
      },
    });
    let data = {};
    try { data = await res.json(); } catch { /* non-JSON response */ }
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    return data;
  }

  // ---------- display helpers ----------
  function showError(msg) { errEl.textContent = msg; }
  function clearError() { errEl.textContent = ""; }

  function insert(text) {
    const start = exprEl.selectionStart ?? exprEl.value.length;
    const end = exprEl.selectionEnd ?? start;
    exprEl.setRangeText(text, start, end, "end");
    exprEl.focus();
    clearError();
  }

  function backspace() {
    const start = exprEl.selectionStart ?? exprEl.value.length;
    const end = exprEl.selectionEnd ?? start;
    if (start !== end) exprEl.setRangeText("", start, end, "end");
    else if (start > 0) exprEl.setRangeText("", start - 1, start, "end");
    exprEl.focus();
    clearError();
  }

  function clearAll() {
    exprEl.value = "";
    prevEl.textContent = "";
    clearError();
    exprEl.focus();
  }

  function refreshIndicators() {
    modeBtn.textContent = angle;
    memInd.classList.toggle("hidden", memory === 0);
  }

  // ---------- calculation ----------
  async function evaluate() {
    const expression = exprEl.value.trim();
    if (!expression) return null;
    clearError();
    try {
      const data = await api("/api/calculate", {
        method: "POST",
        body: JSON.stringify({ expression, angle_mode: angle, ans, memory }),
      });
      prevEl.textContent = `${data.expression} =`;
      exprEl.value = data.formatted;
      if (data.value !== null) {
        ans = data.value;
        store.set("ans", String(ans));
      }
      loadHistory();
      return data;
    } catch (err) {
      showError(err.message);
      return null;
    }
  }

  async function memoryAdd(sign) {
    const data = exprEl.value.trim() ? await evaluate() : { value: ans };
    if (!data || data.value === null) return;
    memory += sign * data.value;
    store.set("memory", String(memory));
    refreshIndicators();
  }

  function memoryRecall() {
    const text = String(memory);
    insert(memory < 0 ? `(${text})` : text);
  }

  function memoryClear() {
    memory = 0;
    store.set("memory", "0");
    refreshIndicators();
  }

  function toggleAngle() {
    angle = angle === "DEG" ? "RAD" : "DEG";
    store.set("angle", angle);
    refreshIndicators();
  }

  // ---------- keypad ----------
  // [label, kind, action]  action: string = text to insert, function = custom handler
  const fn = (name) => `${name}(`;
  const layout = [
    [["MC", "mem", memoryClear], ["MR", "mem", memoryRecall], ["M+", "mem", () => memoryAdd(1)],
     ["M−", "mem", () => memoryAdd(-1)], ["⌫", "ctl", backspace], ["C", "ctl", clearAll], ["(", "op", "("]],
    [["sin", "fn", fn("sin")], ["cos", "fn", fn("cos")], ["tan", "fn", fn("tan")],
     ["7", "num", "7"], ["8", "num", "8"], ["9", "num", "9"], ["÷", "op", "/"]],
    [["asin", "fn", fn("asin")], ["acos", "fn", fn("acos")], ["atan", "fn", fn("atan")],
     ["4", "num", "4"], ["5", "num", "5"], ["6", "num", "6"], ["×", "op", "*"]],
    [["sinh", "fn", fn("sinh")], ["cosh", "fn", fn("cosh")], ["tanh", "fn", fn("tanh")],
     ["1", "num", "1"], ["2", "num", "2"], ["3", "num", "3"], ["−", "op", "-"]],
    [["log", "fn", fn("log")], ["ln", "fn", fn("ln")], ["log₂", "fn", fn("log2")],
     ["0", "num", "0"], [".", "num", "."], ["xʸ", "op", "^"], ["+", "op", "+"]],
    [["√", "fn", fn("sqrt")], ["∛", "fn", fn("cbrt")], ["eˣ", "fn", fn("exp")],
     ["x²", "fn", "^2"], ["10ˣ", "fn", "10^"], ["n!", "fn", "!"], [")", "op", ")"]],
    [["π", "fn", "pi"], ["e", "fn", "e"], ["Ans", "fn", "ans"],
     ["nPr", "fn", fn("npr")], ["nCr", "fn", fn("ncr")], [",", "op", ","], ["%", "op", "%"]],
    [["abs", "fn", fn("abs")], ["gcd", "fn", fn("gcd")], ["lcm", "fn", fn("lcm")],
     ["floor", "fn", fn("floor")], ["ceil", "fn", fn("ceil")], ["=", "eq", evaluate, 2]],
  ];

  function buildKeypad() {
    const frag = document.createDocumentFragment();
    for (const row of layout) {
      for (const [label, kind, action, span] of row) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `key ${kind}`;
        btn.textContent = label;
        if (span) btn.style.gridColumn = `span ${span}`;
        btn.addEventListener("click", () => {
          if (typeof action === "string") insert(action);
          else action();
        });
        frag.appendChild(btn);
      }
    }
    keysEl.appendChild(frag);
  }

  // ---------- history ----------
  async function loadHistory() {
    try {
      const data = await api("/api/history?limit=50");
      renderHistory(data.history);
    } catch { /* history is optional; ignore failures */ }
  }

  function renderHistory(items) {
    histEl.textContent = "";
    emptyHistEl.classList.toggle("hidden", items.length > 0);
    for (const item of items) {
      const li = document.createElement("li");
      const e = document.createElement("div");
      e.className = "h-expr";
      e.textContent = item.expression;
      const r = document.createElement("div");
      r.className = "h-res";
      r.textContent = `= ${item.result}`;
      li.append(e, r);
      li.title = "Click to reuse this expression";
      li.addEventListener("click", () => {
        exprEl.value = item.expression;
        prevEl.textContent = "";
        clearError();
        exprEl.focus();
      });
      histEl.appendChild(li);
    }
  }

  $("#clearHist").addEventListener("click", async () => {
    try {
      await api("/api/history", { method: "DELETE" });
      renderHistory([]);
    } catch (err) { showError(err.message); }
  });

  // ---------- function reference dialog ----------
  let refLoaded = false;
  async function openReference() {
    if (!refLoaded) {
      try {
        const data = await api("/api/functions");
        for (const group of data.groups) {
          const h = document.createElement("h3");
          h.textContent = group.name;
          const grid = document.createElement("div");
          grid.className = "ref-grid";
          for (const item of group.items) {
            const b = document.createElement("button");
            b.type = "button";
            b.className = "ref-item";
            const title = document.createElement("b");
            title.textContent = item.sig;
            const desc = document.createElement("span");
            desc.textContent = item.desc;
            b.append(title, desc);
            b.addEventListener("click", () => {
              const isFunction = item.sig.includes("(");
              insert(isFunction ? `${item.name}(` : item.name);
              refDialog.close();
            });
            grid.appendChild(b);
          }
          refBody.append(h, grid);
        }
        refLoaded = true;
      } catch (err) {
        showError(err.message);
        return;
      }
    }
    refDialog.showModal();
  }

  $("#refBtn").addEventListener("click", openReference);
  $("#closeRef").addEventListener("click", () => refDialog.close());
  refDialog.addEventListener("click", (e) => {
    if (e.target === refDialog) refDialog.close(); // click on backdrop
  });

  // ---------- theme ----------
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
  }
  const prefersDark = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(store.get("theme", prefersDark ? "dark" : "light"));
  $("#themeBtn").addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    applyTheme(next);
    store.set("theme", next);
  });

  // ---------- keyboard ----------
  exprEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); evaluate(); }
    else if (e.key === "Escape") { clearAll(); }
  });
  exprEl.addEventListener("input", clearError);
  document.addEventListener("keydown", (e) => {
    // typing anywhere starts typing into the expression box
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (document.activeElement === exprEl || refDialog.open) return;
    if (document.activeElement && document.activeElement.tagName === "BUTTON") return;
    if (e.key.length === 1) exprEl.focus();
  });

  modeBtn.addEventListener("click", toggleAngle);

  // ---------- start ----------
  buildKeypad();
  refreshIndicators();
  loadHistory();
  exprEl.focus();
})();
