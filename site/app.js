/* ContextMesh site behavior: hero graph canvas, live demo with API fallback,
   scroll reveals, bar/count animations, and nav. No dependencies. */

(function () {
  "use strict";

  var prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var $ = function (sel, ctx) { return (ctx || document).querySelector(sel); };
  var $$ = function (sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); };

  // --------------------------------------------------------------------- nav
  var nav = $("#nav");
  var navLinks = $("#navLinks");
  var navToggle = $("#navToggle");

  function onScrollNav() {
    if (nav) nav.classList.toggle("scrolled", window.scrollY > 12);
  }
  window.addEventListener("scroll", onScrollNav, { passive: true });
  onScrollNav();

  if (navToggle && navLinks) {
    navToggle.addEventListener("click", function () {
      var open = navLinks.classList.toggle("open");
      navToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    navLinks.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", function () {
        navLinks.classList.remove("open");
        navToggle.setAttribute("aria-expanded", "false");
      });
    });
  }

  // active section link
  var sectionLinks = $$('.nav-links a[href^="#"]');
  var sections = sectionLinks.map(function (a) {
    return document.getElementById(a.getAttribute("href").slice(1));
  }).filter(Boolean);

  if ("IntersectionObserver" in window && sections.length) {
    var activeObs = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          sectionLinks.forEach(function (a) {
            a.classList.toggle("active", a.getAttribute("href") === "#" + entry.target.id);
          });
        }
      });
    }, { rootMargin: "-40% 0px -55% 0px" });
    sections.forEach(function (s) { activeObs.observe(s); });
  }

  // ------------------------------------------------------------------ reveal
  var revealEls = $$("[data-reveal]");
  function revealAll() { revealEls.forEach(function (el) { el.classList.add("in"); }); }

  if (prefersReduced || !("IntersectionObserver" in window)) {
    revealAll();
  } else {
    var revealObs = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("in");
          revealObs.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
    revealEls.forEach(function (el) { revealObs.observe(el); });
  }

  // --------------------------------------------------------------- count-up
  function animateCount(el) {
    if (el.dataset.counted) return;
    var target = parseFloat(el.getAttribute("data-count"));
    if (isNaN(target)) { el.dataset.counted = "1"; return; }
    el.dataset.counted = "1";
    var suffix = el.getAttribute("data-suffix") || "";
    if (prefersReduced) { el.textContent = target + suffix; return; }
    var start = performance.now();
    var dur = 1100;
    function tick(now) {
      var t = Math.min(1, (now - start) / dur);
      var eased = 1 - Math.pow(1 - t, 3);
      var val = Math.round(eased * target);
      el.textContent = val + suffix;
      if (t < 1) requestAnimationFrame(tick);
      else el.textContent = target + suffix;
    }
    requestAnimationFrame(tick);
  }

  var countEls = $$("[data-count]");
  if ("IntersectionObserver" in window && !prefersReduced) {
    var countObs = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { animateCount(entry.target); countObs.unobserve(entry.target); }
      });
    }, { threshold: 0.5 });
    countEls.forEach(function (el) { countObs.observe(el); });
  } else {
    countEls.forEach(animateCount);
  }

  // ------------------------------------------------------------------- bars
  var barEls = $$("[data-bar]");
  function animateBars() {
    barEls.forEach(function (bar) {
      var w = bar.getAttribute("data-bar") + "%";
      bar.style.setProperty("--w", w);
      if (prefersReduced) bar.style.width = w;
      else requestAnimationFrame(function () { bar.style.width = w; });
    });
  }
  if ("IntersectionObserver" in window && !prefersReduced) {
    var barObs = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { animateBars(); barObs.disconnect(); }
      });
    }, { threshold: 0.3 });
    var proof = $(".section-proof");
    if (proof) barObs.observe(proof); else animateBars();
  } else {
    animateBars();
  }

  // ----------------------------------------------------------- hero canvas
  var canvas = $("#graphCanvas");
  if (canvas) initHeroCanvas(canvas);

  function initHeroCanvas(c) {
    var ctx = c.getContext("2d");
    if (!ctx) return;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var W = 0, H = 0, t0 = 0, raf = 0;

    // palette
    var C = {
      line: "rgba(58, 79, 107, 0.7)",
      lineHi: "rgba(55, 210, 170, 0.55)",
      blue: "#5aa2ff",
      teal: "#37d2aa",
      ink: "#dbe7f4",
      dim: "#8aa0b8",
      panel: "#0f1620"
    };

    var nodes = [
      { id: "agent", label: "Agent", x: 0.5, y: 0.52, r: 18, fill: C.teal, text: "#06201a", kind: "hub" },
      { id: "skill", label: "incident-triage", x: 0.5, y: 0.18, r: 13, fill: C.blue, text: "#06101f", kind: "skill" },
      { id: "t1", label: "get_pod_status", x: 0.15, y: 0.32, r: 8, fill: "#1b2a3a", stroke: "#3a4f6b", text: C.dim, kind: "tool" },
      { id: "t2", label: "get_events", x: 0.86, y: 0.30, r: 8, fill: "#1b2a3a", stroke: "#3a4f6b", text: C.dim, kind: "tool" },
      { id: "t3", label: "get_metric_series", x: 0.84, y: 0.58, r: 8, fill: "#1b2a3a", stroke: "#3a4f6b", text: C.dim, kind: "tool" },
      { id: "t4", label: "get_ci_status", x: 0.14, y: 0.62, r: 8, fill: "#1b2a3a", stroke: "#3a4f6b", text: C.dim, kind: "tool" },
      { id: "s1", label: "k8s", x: 0.18, y: 0.82, r: 10, fill: "#152132", stroke: "#5aa2ff", text: C.ink, kind: "server" },
      { id: "s2", label: "grafana", x: 0.82, y: 0.82, r: 10, fill: "#152132", stroke: "#5aa2ff", text: C.ink, kind: "server" },
      { id: "e1", label: "checkout-api", x: 0.72, y: 0.10, r: 9, fill: "#12241f", stroke: C.teal, text: C.ink, kind: "entity" },
      { id: "e2", label: "prod-us", x: 0.28, y: 0.10, r: 9, fill: "#12241f", stroke: C.teal, text: C.ink, kind: "entity" }
    ];
    var byId = {};
    nodes.forEach(function (n) { byId[n.id] = n; });

    var edges = [
      ["agent", "skill", "hi"], ["skill", "t1", "lo"], ["skill", "t2", "lo"],
      ["skill", "t3", "lo"], ["skill", "t4", "lo"],
      ["t1", "s1", "lo"], ["t4", "s1", "lo"], ["t2", "s2", "lo"], ["t3", "s2", "lo"],
      ["skill", "e1", "hi"], ["skill", "e2", "hi"]
    ];

    function resize() {
      var rect = c.getBoundingClientRect();
      W = Math.max(1, Math.floor(rect.width));
      H = Math.max(1, Math.floor(rect.height));
      c.width = Math.floor(W * dpr);
      c.height = Math.floor(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    window.addEventListener("resize", resize);

    function draw(now) {
      var t = (now - t0) / 1000;
      ctx.clearRect(0, 0, W, H);

      // subtle ambient ring
      var cx = W * 0.5, cy = H * 0.52;
      var rg = ctx.createRadialGradient(cx, cy, 10, cx, cy, Math.min(W, H) * 0.42);
      rg.addColorStop(0, "rgba(55, 210, 170, 0.06)");
      rg.addColorStop(1, "rgba(55, 210, 170, 0)");
      ctx.fillStyle = rg;
      ctx.fillRect(0, 0, W, H);

      // edges
      edges.forEach(function (e, i) {
        var a = byId[e[0]], b = byId[e[1]];
        var ax = a.x * W, ay = a.y * H, bx = b.x * W, by = b.y * H;
        ctx.beginPath();
        ctx.moveTo(ax, ay);
        ctx.lineTo(bx, by);
        ctx.strokeStyle = e[2] === "hi" ? C.lineHi : C.line;
        ctx.lineWidth = e[2] === "hi" ? 1.6 : 1.1;
        ctx.stroke();

        // pulse
        if (!prefersReduced) {
          var p = ((t * 0.18) + i * 0.13) % 1;
          var px = ax + (bx - ax) * p;
          var py = ay + (by - ay) * p;
          ctx.beginPath();
          ctx.arc(px, py, e[2] === "hi" ? 2.2 : 1.6, 0, Math.PI * 2);
          ctx.fillStyle = e[2] === "hi" ? "rgba(55,210,170,0.9)" : "rgba(90,162,255,0.7)";
          ctx.fill();
        }
      });

      // nodes
      nodes.forEach(function (n, i) {
        var bob = prefersReduced ? 0 : Math.sin(t * 0.9 + i * 0.7) * 2.2;
        var x = n.x * W, y = n.y * H + bob;
        var r = n.kind === "hub" ? n.r + (prefersReduced ? 0 : Math.sin(t * 1.4) * 1.2) : n.r;

        if (n.kind === "hub") {
          ctx.beginPath();
          ctx.arc(x, y, r + 10, 0, Math.PI * 2);
          ctx.fillStyle = "rgba(55,210,170,0.08)";
          ctx.fill();
        }

        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fillStyle = n.fill;
        ctx.fill();
        if (n.stroke) { ctx.strokeStyle = n.stroke; ctx.lineWidth = 1.4; ctx.stroke(); }

        // labels
        ctx.font = (n.kind === "hub" ? "600 12px " : n.kind === "entity" ? "500 11px " : "500 10.5px ") + "ui-monospace, SFMono-Regular, Menlo, monospace";
        ctx.fillStyle = n.kind === "tool" ? "#7f93a8" : "#d6e4f2";
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        var ly = y + r + 6;
        if (n.kind === "skill") ly = y - r - 18;
        if (n.kind === "entity" && n.id === "e1") ly = y - r - 18;
        if (n.kind === "entity" && n.id === "e2") ly = y - r - 18;
        ctx.fillText(n.label, x, ly);
      });

      // tiny "2 round-trips" tag
      ctx.font = "500 11px ui-monospace, SFMono-Regular, Menlo, monospace";
      ctx.fillStyle = "rgba(138,160,184,0.85)";
      ctx.textAlign = "right";
      ctx.textBaseline = "bottom";
      ctx.fillText("plan()  ·  2 round-trips", W - 6, H - 8);

      raf = requestAnimationFrame(draw);
    }

    if (prefersReduced) {
      draw(0);
    } else {
      var running = false;
      var vis = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting && !running) {
            running = true; t0 = performance.now(); raf = requestAnimationFrame(draw);
          } else if (!entry.isIntersecting && running) {
            running = false; cancelAnimationFrame(raf);
          }
        });
      }, { threshold: 0.05 });
      vis.observe(c);
    }
  }

  // ------------------------------------------------------------------- demo
  var taskInput = $("#taskInput");
  var planBtn = $("#planBtn");
  var recordBtn = $("#recordBtn");
  var statusEl = $("#demoStatus");
  var chips = $$("#exampleChips .chip");
  var elSkills = $("#rSkills");
  var elTools = $("#rTools");
  var elEntities = $("#rEntities");
  var elRaw = $("#rawJson");
  var elTrips = $("#mTrips");
  var elMs = $("#mMs");
  var elToolsN = $("#mTools");
  var elServersN = $("#mServers");
  var elToolCount = $("#toolCount");
  var elGraphStats = $("#graphStats");

  var currentPack = null;
  var currentTask = "";
  var apiAvailable = null;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function setStatus(msg, cls) {
    if (!statusEl) return;
    statusEl.innerHTML = cls ? '<span class="' + cls + '">' + esc(msg) + "</span>" : esc(msg);
  }

  function renderPack(pack, task) {
    currentPack = pack;
    currentTask = task;

    // metrics
    if (elTrips) elTrips.textContent = pack.trips != null ? pack.trips : "2";
    if (elMs) elMs.textContent = pack.ms != null ? pack.ms : "—";
    var toolCount = (pack.tools || []).length;
    if (elToolsN) elToolsN.textContent = toolCount;
    if (elServersN) elServersN.textContent = (pack.mcp_servers || []).length;
    if (elToolCount) elToolCount.textContent = toolCount ? "(" + toolCount + ")" : "";

    // skills
    if (elSkills) {
      var skills = pack.skills || [];
      elSkills.innerHTML = skills.length
        ? skills.map(function (s) { return '<span class="pill">' + esc(s) + "</span>"; }).join("")
        : '<span class="pill pill-muted">none</span>';
    }

    // tools
    if (elTools) {
      var tools = pack.tools || [];
      if (!tools.length) {
        elTools.innerHTML = '<li class="tool-item"><span class="tool-name" style="color:var(--dim-2)">No tools bound</span></li>';
      } else {
        elTools.innerHTML = tools.map(function (t) {
          var name = t.tool || t.name || "";
          var server = t.server || "";
          var desc = t.desc || (t.schema_json ? safeDesc(t.schema_json) : "");
          return '<li class="tool-item">' +
            '<span class="tool-name">' + esc(name) + '</span>' +
            (server ? '<span class="tool-server">' + esc(server) + "</span>" : "") +
            (desc ? '<span class="tool-desc">' + esc(desc) + "</span>" : "") +
            "</li>";
        }).join("");
      }
    }

    // entities
    if (elEntities) {
      var ents = pack.entities || pack.resolved_entities || {};
      var keys = Object.keys(ents);
      if (!keys.length) {
        elEntities.innerHTML = '<li class="entity-item"><span class="entity-mention" style="color:var(--dim-2)">No entities resolved</span></li>';
      } else {
        elEntities.innerHTML = keys.map(function (k) {
          var v = ents[k] || {};
          var name = v.name || v;
          var kind = v.kind || "";
          return '<li class="entity-item">' +
            '<span class="entity-mention">“' + esc(k) + '”</span>' +
            '<span class="entity-arrow">→</span>' +
            '<span class="entity-name">' + esc(name) + "</span>" +
            (kind ? '<span class="entity-kind">' + esc(kind) + "</span>" : "") +
            "</li>";
        }).join("");
      }
    }

    // raw
    if (elRaw) {
      try { elRaw.textContent = JSON.stringify(pack, null, 2); } catch (e) { elRaw.textContent = ""; }
    }

    if (recordBtn) recordBtn.disabled = !pack || pack._fallback;
  }

  function safeDesc(schemaJson) {
    try { var o = typeof schemaJson === "string" ? JSON.parse(schemaJson) : schemaJson; return (o && o.description) || ""; }
    catch (e) { return ""; }
  }

  function normalizeApiPack(d) {
    // /v1/plan returns: skills [names], tools [{tool,server,schema_json,...}], mcp_servers [{name,..} or strings], resolved_entities, graph_round_trips, context_ms
    var servers = (d.mcp_servers || []).map(function (s) { return typeof s === "string" ? s : (s.name || ""); }).filter(Boolean);
    var tools = (d.tools || []).map(function (t) {
      return {
        tool: t.tool || t.name,
        server: t.server || "",
        desc: t.desc || safeDesc(t.schema_json)
      };
    });
    var entities = {};
    var re = d.resolved_entities || d.entities || {};
    Object.keys(re).forEach(function (k) {
      var v = re[k];
      entities[k] = typeof v === "string" ? { name: v, kind: "" } : { name: v.name, kind: v.kind || "" };
    });
    return {
      skills: d.skills || [],
      tools: tools,
      mcp_servers: servers,
      entities: entities,
      trips: d.graph_round_trips != null ? d.graph_round_trips : d.trips,
      ms: d.context_ms != null ? d.context_ms : d.ms
    };
  }

  function getFallback(task) {
    var fb = window.FALLBACK_PACKS || {};
    if (fb[task]) return Object.assign({ _fallback: true }, fb[task]);
    // try fuzzy contains
    var t = task.toLowerCase();
    var keys = Object.keys(fb);
    for (var i = 0; i < keys.length; i++) {
      if (t.indexOf(keys[i].split(" ")[0]) !== -1 || keys[i].toLowerCase().indexOf(t.split(" ")[0]) !== -1) {
        return Object.assign({ _fallback: true }, fb[keys[i]]);
      }
    }
    // default first
    return keys.length ? Object.assign({ _fallback: true }, fb[keys[0]]) : null;
  }

  function planTask(task) {
    if (!task) return;
    setStatus("Planning context from the graph…");
    if (planBtn) planBtn.disabled = true;

    var done = function (pack, fromApi) {
      renderPack(pack, task);
      if (fromApi) {
        setStatus("Context loaded live · " + pack.trips + " round-trips, " + pack.ms + " ms", "ok");
      } else {
        setStatus("Showing recorded pack (API unreachable). Run the service for live results.", "err");
      }
      if (planBtn) planBtn.disabled = false;
    };

    // try API with short timeout
    var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    var timer = setTimeout(function () { if (controller) controller.abort(); }, 3500);

    fetch("/v1/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task: task }),
      signal: controller ? controller.signal : undefined
    }).then(function (r) {
      clearTimeout(timer);
      if (r.status === 401) {
        var authErr = new Error("auth");
        authErr.auth = true;
        throw authErr;
      }
      if (!r.ok) throw new Error("bad status");
      return r.json();
    }).then(function (d) {
      apiAvailable = true;
      done(normalizeApiPack(d), true);
      fetchStats();
    }).catch(function (err) {
      clearTimeout(timer);
      apiAvailable = false;
      if (err && err.auth) {
        setStatus("API key required. Set CONTEXTSMESH_API_KEY on the service, or disable it for the demo.", "err");
        if (planBtn) planBtn.disabled = false;
        return;
      }
      var fb = getFallback(task);
      if (fb) done(fb, false);
      else { setStatus("API unreachable and no fallback available.", "err"); if (planBtn) planBtn.disabled = false; }
    });
  }

  function fetchStats() {
    fetch("/v1/stats", { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (s) {
      if (!s || !elGraphStats) return;
      var parts = [];
      ["Skill", "Tool", "MCPServer", "Entity", "Alias", "Session"].forEach(function (k) {
        if (s[k] != null) parts.push(k + " " + s[k]);
      });
      if (parts.length) elGraphStats.textContent = "Graph: " + parts.join(" · ");
    }).catch(function () {});
  }

  function recordSession() {
    if (!currentPack || currentPack._fallback || !apiAvailable) return;
    if (recordBtn) recordBtn.disabled = true;
    setStatus("Recording session…");
    var resolutions = {};
    var ents = currentPack.entities || {};
    Object.keys(ents).forEach(function (k) { resolutions[k] = (ents[k] && ents[k].name) || ents[k]; });
    var tools = (currentPack.tools || []).map(function (t) { return t.tool || t.name; }).filter(Boolean);
    fetch("/v1/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task: currentTask, used_tools: tools, resolutions: resolutions })
    }).then(function (r) { return r.json(); }).then(function (d) {
      setStatus("Session recorded" + (d && d.session_id != null ? " (#" + d.session_id + ")" : "") + ". Usage counters updated.", "ok");
      fetchStats();
    }).catch(function () {
      setStatus("Could not record session.", "err");
    }).finally(function () {
      if (recordBtn) recordBtn.disabled = false;
    });
  }

  if (planBtn) {
    planBtn.addEventListener("click", function () { planTask((taskInput && taskInput.value || "").trim()); });
  }
  if (taskInput) {
    taskInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); planTask(taskInput.value.trim()); }
    });
  }
  if (recordBtn) recordBtn.addEventListener("click", recordSession);

  chips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      var task = chip.getAttribute("data-task") || chip.textContent;
      if (taskInput) taskInput.value = task;
      chips.forEach(function (c) { c.setAttribute("aria-pressed", c === chip ? "true" : "false"); });
      planTask(task);
    });
  });

  // init: mark first chip and run initial plan
  if (chips[0]) chips[0].setAttribute("aria-pressed", "true");
  planTask((taskInput && taskInput.value) || "why is checkout failing in prod");

  // also try to get stats early (and detect api)
  fetch("/health", { cache: "no-store" }).then(function (r) {
    if (r.ok) { apiAvailable = true; fetchStats(); }
  }).catch(function () { apiAvailable = false; });

  // ------------------------------------------------------------------ tabs
  $$("[data-tabs]").forEach(function (root) {
    var tabs = $$(".tab", root);
    var panels = $$(".tab-panel", root);
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var id = tab.getAttribute("data-tab");
        tabs.forEach(function (t) {
          var on = t === tab;
          t.classList.toggle("active", on);
          t.setAttribute("aria-selected", on ? "true" : "false");
        });
        panels.forEach(function (p) {
          p.classList.toggle("active", p.getAttribute("data-panel") === id);
        });
      });
    });
  });

  // ----------------------------------------------------------- pilot dialog
  var pilotDialog = $("#pilotDialog");
  var pilotForm = $("#pilotForm");
  var pilotStatus = $("#pilotStatus");
  var pilotSubmit = $("#pilotSubmit");

  function openPilot() {
    if (!pilotDialog) return;
    if (typeof pilotDialog.showModal === "function") pilotDialog.showModal();
    else pilotDialog.setAttribute("open", "open");
    setTimeout(function () {
      var first = $("#pName");
      if (first) first.focus();
    }, 30);
  }

  function closePilot() {
    if (!pilotDialog) return;
    if (typeof pilotDialog.close === "function") pilotDialog.close();
    else pilotDialog.removeAttribute("open");
  }

  $$(".js-pilot").forEach(function (btn) {
    btn.addEventListener("click", openPilot);
  });

  ["#pilotClose", "#pilotCancel"].forEach(function (sel) {
    var el = $(sel);
    if (el) el.addEventListener("click", closePilot);
  });

  if (pilotDialog) {
    pilotDialog.addEventListener("click", function (e) {
      if (e.target === pilotDialog) closePilot();  // click the backdrop
    });
  }

  if (pilotForm) {
    pilotForm.addEventListener("submit", function (e) {
      e.preventDefault();
      if (pilotStatus) { pilotStatus.textContent = "Sending…"; pilotStatus.className = "pilot-status"; }
      if (pilotSubmit) pilotSubmit.disabled = true;

      var payload = {
        name: ($("#pName") || {}).value || "",
        email: ($("#pEmail") || {}).value || "",
        company: ($("#pCompany") || {}).value || "",
        note: ($("#pNote") || {}).value || ""
      };

      fetch("/v1/pilot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }).then(function (r) {
        return r.json().then(function (body) { return { ok: r.ok, body: body }; });
      }).then(function (res) {
        if (!res.ok) {
          var msg = (res.body && res.body.error && res.body.error.message) || "Could not send the request.";
          throw new Error(msg);
        }
        if (pilotStatus) { pilotStatus.textContent = res.body.message || "Thanks — we’ll be in touch."; pilotStatus.className = "pilot-status ok"; }
        pilotForm.reset();
        if (pilotSubmit) pilotSubmit.disabled = false;
        setTimeout(closePilot, 1800);
      }).catch(function (err) {
        if (pilotStatus) { pilotStatus.textContent = err.message || "Could not send the request."; pilotStatus.className = "pilot-status err"; }
        if (pilotSubmit) pilotSubmit.disabled = false;
      });
    });
  }

})();
