/* Live updates without a page reload.
   Every few seconds this fetches the current page again and swaps only the parts marked
   data-live="..." (never forms the user may be typing in). New notifications pop up as a toast. */
(function () {
  "use strict";
  var INTERVAL_MS = 4000;
  var timer = null, lastOk = Date.now(), busy = false, failures = 0;
  var prevUnread = null;

  // ---- small "Live" indicator, bottom-left ----
  var pill = document.createElement("div");
  pill.className = "live-pill";
  pill.setAttribute("role", "status");
  pill.innerHTML = '<span class="live-dot"></span><span class="live-text">Live</span>';
  document.body.appendChild(pill);
  var pillText = pill.querySelector(".live-text");

  function setPill(state) {
    pill.classList.toggle("is-offline", state === "offline");
    pill.classList.toggle("is-paused", state === "paused");
    if (state === "offline") pillText.textContent = "Offline - retrying";
    else if (state === "paused") pillText.textContent = "Paused";
    else pillText.textContent = "Live · updated " + Math.max(0, Math.round((Date.now() - lastOk) / 1000)) + "s ago";
  }
  setInterval(function () { if (!document.hidden && failures === 0) setPill("ok"); }, 1000);

  // ---- toast for new notifications ----
  function toast(message) {
    var box = document.getElementById("liveToasts");
    if (!box || !message || !window.bootstrap) return;
    var el = document.createElement("div");
    el.className = "toast live-toast border-0";
    el.setAttribute("role", "alert");
    el.innerHTML =
      '<div class="d-flex"><div class="toast-body"><i class="bi bi-bell-fill me-2"></i></div>' +
      '<button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button></div>';
    el.querySelector(".toast-body").appendChild(document.createTextNode(message)); // text only, never HTML
    box.appendChild(el);
    var t = new bootstrap.Toast(el, { delay: 7000 });
    el.addEventListener("hidden.bs.toast", function () { el.remove(); });
    t.show();
  }

  // ---- swap changed regions ----
  function applyUpdate(doc) {
    var changed = false;
    var regions = document.querySelectorAll("[data-live]");
    regions.forEach(function (cur) {
      var fresh = doc.querySelector('[data-live="' + cur.getAttribute("data-live") + '"]');
      if (!fresh) return;
      if (cur.contains(document.activeElement) && /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) return;
      if (cur.innerHTML.trim() === fresh.innerHTML.trim()) {
        // keep data-* attributes (used for the bell) in sync even if the markup is equal
        return;
      }
      cur.innerHTML = fresh.innerHTML;
      Array.prototype.forEach.call(fresh.attributes, function (a) {
        if (a.name.indexOf("data-") === 0) cur.setAttribute(a.name, a.value);
      });
      if (cur.id !== "bell-badge" && cur.id !== "bell-menu") {
        cur.classList.remove("live-flash");
        void cur.offsetWidth;            // restart the highlight animation
        cur.classList.add("live-flash");
      }
      changed = true;
    });

    var badge = doc.getElementById("bell-badge");
    if (badge) {
      var unread = parseInt(badge.getAttribute("data-unread") || "0", 10);
      if (prevUnread !== null && unread > prevUnread) toast(badge.getAttribute("data-latest"));
      prevUnread = unread;
    }
    return changed;
  }

  function poll() {
    if (busy || document.hidden) return;
    busy = true;
    fetch(window.location.href, {
      credentials: "same-origin",
      cache: "no-store",
      headers: { "X-Requested-With": "live-refresh" }
    }).then(function (res) {
      var path = new URL(res.url).pathname;
      if (res.redirected && path !== window.location.pathname) {
        // signed out -> stop; moved to another page (e.g. approved guardian) -> follow it
        if (path === "/login") { stop(); setPill("paused"); return null; }
        window.location.href = res.url; return null;
      }
      if (!res.ok) throw new Error("HTTP " + res.status);
      return res.text();
    }).then(function (html) {
      if (html === null || html === undefined) return;
      applyUpdate(new DOMParser().parseFromString(html, "text/html"));
      lastOk = Date.now(); failures = 0; setPill("ok");
    }).catch(function () {
      failures += 1; setPill("offline");
    }).then(function () { busy = false; });
  }

  function start() { if (!timer) timer = setInterval(poll, INTERVAL_MS); }
  function stop() { if (timer) { clearInterval(timer); timer = null; } }

  // remember the starting unread count so only NEW notifications trigger a toast
  var first = document.getElementById("bell-badge");
  if (first) prevUnread = parseInt(first.getAttribute("data-unread") || "0", 10);

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) { setPill("paused"); } else { poll(); }
  });
  start();
})();
