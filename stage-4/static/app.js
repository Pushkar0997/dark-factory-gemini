/* Tablekeeper browser client. Plain JS, no external assets. */
(function () {
  "use strict";

  // ------------------------------------------------------------ helpers

  function h(tag, attrs) {
    var el = document.createElement(tag);
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === "testid") el.setAttribute("data-testid", v);
      else if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
      else if (k === "value") el.value = v;
      else el.setAttribute(k, v === true ? "" : v);
    });
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c === null || c === undefined || c === false) continue;
      if (Array.isArray(c)) c.forEach(function (x) { if (x) el.appendChild(typeof x === "string" ? document.createTextNode(x) : x); });
      else el.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return el;
  }

  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }
  function $(id) { return document.getElementById(id); }

  function newKey() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    var s = "";
    for (var i = 0; i < 32; i++) s += Math.floor(Math.random() * 16).toString(16);
    return s;
  }

  function todayLocal() {
    var d = new Date();
    var p = function (n) { return (n < 10 ? "0" : "") + n; };
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
  }

  function hhmm(local) { return local.slice(11, 16); }

  function prettyDate(local) {
    var y = +local.slice(0, 4), m = +local.slice(5, 7), d = +local.slice(8, 10);
    try {
      return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB",
        { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
    } catch (e) { return local.slice(0, 10); }
  }

  function prettyWhen(local) { return prettyDate(local) + " · " + hhmm(local); }

  var ERRORS = {
    table_unavailable: "Sorry — that table was just taken. We've refreshed availability so you can pick another table or time.",
    outside_opening_hours: "The restaurant isn't open for the whole of that booking.",
    not_on_slot_grid: "Bookings start on the restaurant's time slots.",
    party_exceeds_capacity: "That party is too large for this table.",
    combination_not_allowed: "Those tables can't be combined.",
    invalid_local_time: "That time doesn't exist on this date (clocks change).",
    validation_failed: "Please check the details and try again.",
    unauthenticated: "Please sign in again to continue.",
    cutoff_passed: "It's too close to the booking time to change or cancel it.",
    reservation_cancelled: "This booking has already been cancelled.",
    not_found: "We couldn't find that."
  };

  function errorText(body, fallback) {
    var e = body && body.error;
    if (!e) return fallback || "Something went wrong. Please try again.";
    return ERRORS[e.code] || e.message || fallback;
  }

  // ------------------------------------------------------------ session + API

  var SESSION_KEY = "tablekeeper.session";

  function getSession() {
    try { return JSON.parse(localStorage.getItem(SESSION_KEY)) || null; } catch (e) { return null; }
  }
  function setSession(s) {
    if (s) localStorage.setItem(SESSION_KEY, JSON.stringify(s));
    else localStorage.removeItem(SESSION_KEY);
    renderNav();
  }

  // Resolves {status, body}; rejects only when no HTTP response arrived.
  function api(method, path, body, extraHeaders) {
    var headers = { "Accept": "application/json" };
    var s = getSession();
    if (s && s.token) headers["Authorization"] = "Bearer " + s.token;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    Object.keys(extraHeaders || {}).forEach(function (k) { headers[k] = extraHeaders[k]; });
    return fetch(path, {
      method: method, headers: headers, cache: "no-store",
      body: body === undefined ? undefined : JSON.stringify(body)
    }).then(function (resp) {
      return resp.text().then(function (txt) {
        var parsed = null;
        if (txt) { try { parsed = JSON.parse(txt); } catch (e) { parsed = undefined; } }
        return { status: resp.status, body: parsed };
      });
    });
  }

  // ------------------------------------------------------------ nav + routing

  function renderNav() {
    var s = getSession();
    var box = clear($("auth-nav"));
    if (s && s.token) {
      box.appendChild(h("span", { class: "user-chip", testid: "current-user", title: "Signed in" },
        "Signed in as " + s.display_name));
      box.appendChild(h("button", { class: "btn btn-quiet", testid: "logout-button", type: "button",
        onclick: function () { setSession(null); render(); } }, "Log out"));
    } else {
      box.appendChild(h("a", { href: "/login", "data-link": true, "data-nav": "/login" }, "Log in"));
      box.appendChild(h("a", { href: "/signup", "data-link": true, "data-nav": "/signup" }, "Sign up"));
    }
    markActive();
  }

  function markActive() {
    var path = location.pathname;
    Array.prototype.forEach.call(document.querySelectorAll("[data-nav]"), function (a) {
      a.classList.toggle("active", a.getAttribute("data-nav") === path);
      if (a.getAttribute("data-nav") === path) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
  }

  function go(path) {
    if (location.pathname !== path) history.pushState({}, "", path);
    render();
  }

  document.addEventListener("click", function (ev) {
    var a = ev.target.closest && ev.target.closest("a[data-link]");
    if (!a || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button !== 0) return;
    ev.preventDefault();
    go(a.getAttribute("href"));
  });
  window.addEventListener("popstate", render);

  var pageToken = 0; // invalidates async work of a page that has been left

  function render() {
    pageToken++;
    renderNav();
    var main = clear($("main"));
    var path = location.pathname.replace(/\/+$/, "") || "/";
    if (path === "/signup") renderAuth(main, "signup");
    else if (path === "/login") renderAuth(main, "login");
    else if (path === "/lookup") renderLookup(main);
    else renderHome(main);
  }

  // ------------------------------------------------------------ auth screens

  function renderAuth(main, mode) {
    var isSignup = mode === "signup";
    var p = isSignup ? "signup-" : "login-";
    var errBox = h("div", { "aria-live": "polite" });
    var email = h("input", { id: p + "email", type: "email", testid: p + "email", autocomplete: "email", required: true });
    var pw = h("input", { id: p + "password", type: "password", testid: p + "password",
      autocomplete: isSignup ? "new-password" : "current-password", required: true });
    var name = isSignup ? h("input", { id: "signup-display-name", type: "text", testid: "signup-display-name", autocomplete: "name" }) : null;
    var submit = h("button", { class: "btn btn-primary", type: "submit", testid: p + "submit" },
      isSignup ? "Create account" : "Log in");

    function showError(msg) {
      clear(errBox).appendChild(h("p", { class: "notice notice-error", testid: "auth-error", role: "alert" }, msg));
    }

    var form = h("form", { class: "stack", novalidate: true, onsubmit: function (ev) {
      ev.preventDefault();
      clear(errBox);
      submit.disabled = true;
      var body = { email: email.value.trim(), password: pw.value };
      if (isSignup) body.display_name = name.value.trim();
      var token = pageToken;
      api("POST", isSignup ? "/auth/signup" : "/auth/login", body).then(function (r) {
        if (token !== pageToken) return;
        submit.disabled = false;
        if (r.status === 200 || r.status === 201) {
          setSession({ token: r.body.token, user_id: r.body.user_id, display_name: r.body.display_name });
          go("/");
        } else if (r.status === 401) {
          showError("That email and password don't match an account.");
        } else if (r.status === 409) {
          showError("An account with this email already exists. Try logging in.");
        } else if (r.status === 422) {
          showError(isSignup ? "Use a valid email and a password of at least 8 characters." : "Enter your email and password.");
        } else {
          showError(errorText(r.body));
        }
      }, function () {
        if (token !== pageToken) return;
        submit.disabled = false;
        showError("We couldn't reach Tablekeeper. Check your connection and try again.");
      });
    } },
      h("div", { class: "field" }, h("label", { for: p + "email" }, "Email"), email),
      h("div", { class: "field" }, h("label", { for: p + "password" }, "Password"), pw,
        isSignup ? h("small", { class: "lede" }, "At least 8 characters.") : null),
      isSignup ? h("div", { class: "field" }, h("label", { for: "signup-display-name" }, "Your name"), name) : null,
      submit, errBox,
      h("p", { class: "lede" }, isSignup ? "Already have an account? " : "New here? ",
        h("a", { href: isSignup ? "/login" : "/signup", "data-link": true }, isSignup ? "Log in" : "Create an account")));

    main.appendChild(h("section", { class: "card narrow" },
      h("h1", {}, isSignup ? "Create your account" : "Welcome back"),
      h("p", { class: "lede" }, isSignup ? "Book tables and manage your reservations." : "Log in to book and manage your tables."),
      form));
  }

  // ------------------------------------------------------------ home: search + grid + booking

  var searchState = { restaurant: null, date: null, party: "2" };
  var searchSeq = 0;
  var current = null;     // {params, detail, availability} for the latest rendered search
  var selection = null;   // the open booking form
  var restaurantsCache = null;

  function renderHome(main) {
    var token = pageToken;
    selection = null;
    current = null;
    searchSeq++;

    var select = h("select", { id: "restaurant-select", testid: "restaurant-select" });
    var date = h("input", { id: "date-input", type: "date", testid: "date-input", value: searchState.date || todayLocal() });
    var party = h("input", { id: "party-size-input", type: "number", min: "1", step: "1", inputmode: "numeric",
      testid: "party-size-input", value: searchState.party || "2" });
    var searchBtn = h("button", { class: "btn btn-primary", type: "submit", testid: "search-button" }, "Find a table");

    var form = h("form", { class: "search-form", onsubmit: function (ev) {
      ev.preventDefault();
      searchState = { restaurant: select.value, date: date.value, party: party.value };
      runSearch({ restaurant: select.value, date: date.value, party: party.value }, false);
    } },
      h("div", { class: "field field-restaurant" }, h("label", { for: "restaurant-select" }, "Restaurant"), select),
      h("div", { class: "field" }, h("label", { for: "date-input" }, "Date"), date),
      h("div", { class: "field" }, h("label", { for: "party-size-input" }, "Guests"), party),
      h("div", { class: "search-go" }, searchBtn));

    main.appendChild(h("h1", {}, "Find a table"));
    main.appendChild(h("p", { class: "lede" }, "Choose a restaurant, a date and your party size, then pick a time and table."));
    main.appendChild(h("section", { class: "card" }, form));
    main.appendChild(h("div", { class: "layout" },
      h("section", { class: "card", "aria-live": "polite" }, h("div", { id: "home-notice" }),
        h("div", { id: "results" }, h("p", { class: "empty" }, "Your available times will appear here."))),
      h("aside", { id: "booking", class: "booking" })));

    function fill(list) {
      clear(select);
      list.forEach(function (r) { select.appendChild(h("option", { value: r.id }, r.name || r.id)); });
      if (!list.length) select.appendChild(h("option", { value: "" }, "No restaurants yet"));
      if (searchState.restaurant) select.value = searchState.restaurant;
    }
    if (restaurantsCache) fill(restaurantsCache);
    api("GET", "/restaurants").then(function (r) {
      if (token !== pageToken || r.status !== 200) return;
      restaurantsCache = r.body.restaurants;
      var keep = select.value;
      fill(restaurantsCache);
      if (keep && restaurantsCache.some(function (x) { return x.id === keep; })) select.value = keep;
    }, function () {});
  }

  function notice(msg, kind, testid) {
    var box = $("home-notice");
    if (!box) return;
    clear(box);
    if (msg) box.appendChild(h("p", { class: "notice notice-" + (kind || "error"), testid: testid || null, role: "alert" }, msg));
  }

  // keepForm: a refresh after a booking attempt; a user search replaces everything.
  function runSearch(params, keepForm) {
    var seq = ++searchSeq;
    var token = pageToken;
    var results = $("results");
    if (!keepForm) {
      selection = null;
      renderBooking();
      notice(null);
      clear(results).appendChild(h("p", { class: "loading", role: "status" }, "Checking availability…"));
    }
    var q = "/availability?restaurant_id=" + encodeURIComponent(params.restaurant) +
      "&date=" + encodeURIComponent(params.date) + "&party_size=" + encodeURIComponent(params.party) + "&explain=true";
    Promise.all([api("GET", "/restaurants/" + encodeURIComponent(params.restaurant)), api("GET", q),
      api("GET", "/restaurants/" + encodeURIComponent(params.restaurant) + "/policies")]).then(function (rs) {
      if (seq !== searchSeq || token !== pageToken) return; // a newer search owns the screen
      var d = rs[0], a = rs[1];
      if (d.status !== 200 || a.status !== 200) {
        current = null;
        clear(results).appendChild(h("p", { class: "notice notice-error", role: "alert" },
          a.status === 422 ? "Please choose a restaurant, a valid date and a party size of at least 1." : errorText(a.body || d.body)));
        return;
      }
      current = { params: params, detail: d.body, availability: a.body,
        capacities: capacitiesFor(d.body, rs[2].status === 200 ? rs[2].body.policies : [], params.date) };
      renderGrid();
    }, function () {
      if (seq !== searchSeq || token !== pageToken) return;
      if (!keepForm) clear(results).appendChild(h("p", { class: "notice notice-error", role: "alert" },
        "We couldn't reach Tablekeeper. Check your connection and search again."));
    });
  }

  // Seat counts in force on a date: the published policy with the greatest effective_from
  // not later than the date (ties: greatest version), else the restaurant's own tables.
  function capacitiesFor(detail, policies, date) {
    var best = null;
    (policies || []).forEach(function (p) {
      if (p.effective_from > date) return;
      if (!best || p.effective_from > best.effective_from ||
          (p.effective_from === best.effective_from && p.policy_version > best.policy_version)) best = p;
    });
    if (best) return best.capacities;
    var caps = {};
    (detail.tables || []).forEach(function (t) { caps[t.id] = t.capacity; });
    return caps;
  }

  function tableLabel(detail, id) {
    var t = (detail.tables || []).filter(function (x) { return x.id === id; })[0];
    return t ? (t.label || t.id) : id;
  }
  function tablesText(detail, ids) {
    var labels = ids.map(function (id) { return tableLabel(detail, id); });
    return (labels.length > 1 ? "Tables " : "Table ") + labels.join(" + ");
  }

  function renderGrid() {
    var results = clear($("results"));
    var detail = current.detail, av = current.availability;
    if (!av.slots.length) {
      results.appendChild(h("div", { class: "empty", testid: "no-slots" },
        h("h2", {}, "No tables on this day"),
        h("p", {}, detail.name + " isn't taking bookings on " + prettyDate(av.date + "T00:00") + ". Try another date.")));
      return;
    }
    var grid = h("div", { testid: "availability-grid", class: "grid", role: "list" });
    av.slots.forEach(function (slot) {
      var at = hhmm(slot.starts_at_local);
      var cells = h("div", { class: "cells" });
      (detail.tables || []).forEach(function (t) {
        var free = slot.available_table_ids.indexOf(t.id) >= 0;
        cells.appendChild(cell(slot, [t.id], free, current.capacities[t.id], false));
      });
      (slot.available_options || []).forEach(function (opt) {
        if (opt.table_ids.length === 2) cells.appendChild(cell(slot, opt.table_ids, true, opt.capacity, true));
      });
      grid.appendChild(h("div", { class: "slot-row", role: "listitem" },
        h("div", { class: "slot-time" }, at), cells));
    });
    results.appendChild(h("h2", {}, detail.name + " · " + prettyDate(av.date + "T00:00")));
    results.appendChild(h("div", { class: "legend", "aria-hidden": "true" },
      h("span", { class: "lg-free" }, "Available"), h("span", { class: "lg-taken" }, "Taken"),
      h("span", { class: "lg-sel" }, "Your choice")));
    results.appendChild(grid);
  }

  function cell(slot, ids, free, capacity, combo) {
    var at = hhmm(slot.starts_at_local);
    var detail = current.detail;
    var isSel = selection && selection.startsLocal === slot.starts_at_local &&
      selection.tableIds.join("+") === ids.join("+");
    var label = tablesText(detail, ids);
    var b = h("button", {
      type: "button", testid: "slot-" + ids.join("+") + "-" + at,
      "data-available": free ? "true" : "false",
      class: "cell" + (combo ? " combo" : "") + (isSel ? " selected" : ""),
      disabled: !free,
      "aria-pressed": isSel ? "true" : "false",
      "aria-label": label + " at " + at + (free ? ", available" : ", taken") + ", " + capacity + " seats",
      onclick: function () { if (free) openForm(slot, ids); }
    }, h("b", {}, label), h("small", {}, capacity + (capacity === 1 ? " seat" : " seats") + (combo ? " · combined" : "") + (free ? "" : (tooSmall(slot, ids) ? " · too small" : " · taken"))));
    return b;
  }

  // The policy-aware reason a single table is unavailable (from explain=true).
  function tooSmall(slot, ids) {
    var e = (slot.explain || []).filter(function (x) { return x.table_id === ids[0]; })[0];
    return !!(e && ids.length === 1 && !e.rules[0].holds);
  }

  function openForm(slot, ids) {
    if (!getSession()) {
      notice(null);
      var box = $("home-notice");
      box.appendChild(h("p", { class: "notice notice-error", testid: "auth-error", role: "alert" },
        "Please ", h("a", { href: "/login", "data-link": true }, "log in"), " or ",
        h("a", { href: "/signup", "data-link": true }, "create an account"), " to book a table."));
      return;
    }
    notice(null);
    selection = {
      restaurantId: current.detail.id, restaurantName: current.detail.name, detail: current.detail,
      tableIds: ids.slice(), startsLocal: slot.starts_at_local, party: current.params.party,
      pending: null,      // {key, canon} — the identity of the last submitted request
      confirmation: null, error: null, uncertain: null, busy: false
    };
    renderGrid();
    renderBooking();
    var f = document.querySelector("[data-testid='booking-party-size']");
    if (f) f.focus();
  }

  function renderBooking() {
    var box = $("booking");
    if (!box) return;
    clear(box);
    if (!selection) return;
    var s = selection;
    var party = h("input", { id: "booking-party-size", type: "number", min: "1", step: "1", inputmode: "numeric",
      testid: "booking-party-size", value: s.party,
      oninput: function () { s.party = party.value; } });
    var submit = h("button", { class: "btn btn-primary", type: "submit", testid: "booking-submit", disabled: s.busy },
      s.busy ? "Booking…" : (s.uncertain ? "Check & confirm booking" : "Confirm booking"));
    var form = h("form", { class: "card stack", testid: "booking-form", "aria-label": "Booking", onsubmit: function (ev) {
      ev.preventDefault();
      submitBooking();
    } },
      h("h2", {}, "Your table"),
      h("p", { class: "summary", testid: "booking-summary" },
        h("strong", {}, tablesText(s.detail, s.tableIds)),
        s.restaurantName + " · " + prettyWhen(s.startsLocal)),
      h("div", { class: "field" }, h("label", { for: "booking-party-size" }, "Guests"), party),
      submit,
      s.error ? h("p", { class: "notice notice-error", testid: "booking-error", role: "alert" }, s.error) : null,
      s.uncertain ? h("p", { class: "notice notice-warn", testid: "booking-uncertain", role: "status" }, s.uncertain) : null,
      h("button", { class: "btn btn-quiet", type: "button", onclick: function () { selection = null; renderBooking(); if (current) renderGrid(); } }, "Close"));
    box.appendChild(form);
    if (s.confirmation) box.appendChild(renderConfirmation(s.confirmation, s));
  }

  function renderConfirmation(res, s) {
    var tables = tablesText(s.detail, res.table_ids || [res.table_id]);
    return h("section", { class: "card confirm", testid: "confirmation", role: "status" },
      h("h2", {}, "You're booked!"),
      h("p", {}, "Your reference"),
      h("p", { class: "ref", testid: "confirmation-reference" }, res.reference),
      h("div", { testid: "confirmation-details" },
        h("dl", { class: "detail-grid" },
          h("dt", {}, "Restaurant"), h("dd", {}, s.restaurantName),
          h("dt", {}, "Tables"), h("dd", { testid: "confirmation-tables" }, tables),
          h("dt", {}, "When"), h("dd", {}, prettyWhen(res.starts_at_local)),
          h("dt", {}, "Guests"), h("dd", {}, String(res.party_size)))),
      h("p", { class: "lede" }, "Keep your reference to look up or cancel this booking."));
  }

  function bookingBody(s) {
    var n = String(s.party).trim();
    var body = { restaurant_id: s.restaurantId, starts_at_local: s.startsLocal,
      party_size: /^[0-9]+$/.test(n) ? parseInt(n, 10) : n };
    if (s.tableIds.length === 1) body.table_id = s.tableIds[0];
    else body.table_ids = s.tableIds.slice();
    return body;
  }

  function submitBooking() {
    var s = selection;
    if (!s || s.busy) return;
    var body = bookingBody(s);
    var canon = JSON.stringify(body);
    if (!s.pending || s.pending.canon !== canon) {
      // A changed form is a new booking request with a new identity (§7).
      s.pending = { key: newKey(), canon: canon };
      s.confirmation = null;
    }
    var key = s.pending.key;
    s.busy = true;
    renderBooking();
    var token = pageToken;
    api("POST", "/reservations", body, { "Idempotency-Key": key }).then(function (r) {
      if (token !== pageToken || selection !== s) return;
      s.busy = false;
      if (r.status === 200 || r.status === 201) {
        if (!r.body || !r.body.reference) { lost(s); return; }
        s.error = null; s.uncertain = null; s.confirmation = r.body;
        renderBooking();
        if (current) runSearch(current.params, true);
      } else if (r.status >= 500 || r.body === undefined) {
        lost(s);
      } else {
        s.uncertain = null;
        s.confirmation = null;
        s.error = errorText(r.body, "We couldn't make this booking.");
        if (r.status === 401) { s.error = ERRORS.unauthenticated; }
        renderBooking();
        if (r.body && r.body.error && r.body.error.code === "table_unavailable" && current) runSearch(current.params, true);
      }
    }, function () {
      if (token !== pageToken || selection !== s) return;
      s.busy = false;
      lost(s);
    });
  }

  function lost(s) {
    s.error = null;
    s.uncertain = "We couldn't confirm whether your booking went through. Press the button again to check — " +
      "we'll use the same request, so you won't be booked twice.";
    renderBooking();
  }

  // ------------------------------------------------------------ lookup

  function renderLookup(main) {
    var token = pageToken;
    var seq = 0;
    var input = h("input", { id: "lookup-reference-input", type: "text", testid: "lookup-reference-input",
      autocomplete: "off", autocapitalize: "characters", spellcheck: "false" });
    var out = h("div", { "aria-live": "polite" });

    function showError(msg) {
      clear(out).appendChild(h("p", { class: "notice notice-error", testid: "reservation-error", role: "alert" }, msg));
    }

    function lookup(ref) {
      var mine = ++seq;
      if (!getSession()) {
        clear(out).appendChild(h("p", { class: "notice notice-error", testid: "reservation-error", role: "alert" },
          "Please ", h("a", { href: "/login", "data-link": true }, "log in"), " to look up your booking."));
        return;
      }
      clear(out).appendChild(h("p", { class: "loading", role: "status" }, "Looking up your booking…"));
      api("GET", "/reservations/" + encodeURIComponent(ref)).then(function (r) {
        if (mine !== seq || token !== pageToken) return;
        if (r.status !== 200) {
          showError(r.status === 404 ? "We couldn't find a booking with that reference on your account."
            : errorText(r.body));
          return;
        }
        return api("GET", "/restaurants/" + encodeURIComponent(r.body.restaurant_id)).then(function (d) {
          if (mine !== seq || token !== pageToken) return;
          showDetail(r.body, d.status === 200 ? d.body : { name: r.body.restaurant_id, tables: [] }, null);
        });
      }).catch(function () {
        if (mine !== seq || token !== pageToken) return;
        showError("We couldn't reach Tablekeeper. Check your connection and try again.");
      });
    }

    function showDetail(res, detail, errMsg) {
      clear(out);
      var cancel = res.status === "confirmed" ? h("button", { class: "btn btn-danger", type: "button",
        testid: "reservation-cancel-button", onclick: function () {
          cancel.disabled = true;
          var mine = ++seq;
          api("POST", "/reservations/" + encodeURIComponent(res.reference) + "/cancel").then(function (r) {
            if (mine !== seq || token !== pageToken) return;
            if (r.status === 200) showDetail(r.body, detail, null);
            else showDetail(res, detail, errorText(r.body, "We couldn't cancel this booking."));
          }, function () {
            if (mine !== seq || token !== pageToken) return;
            showDetail(res, detail, "We couldn't reach Tablekeeper, so the booking may not be cancelled. Look it up again to check.");
          });
        } }, "Cancel booking") : null;
      out.appendChild(h("section", { class: "card", testid: "reservation-detail" },
        h("h2", {}, detail.name || res.restaurant_id),
        h("dl", { class: "detail-grid" },
          h("dt", {}, "Reference"), h("dd", { class: "ref" }, res.reference),
          h("dt", {}, "Status"), h("dd", {}, h("span", { class: "status status-" + res.status, testid: "reservation-status" }, res.status)),
          h("dt", {}, "Tables"), h("dd", { testid: "reservation-tables" }, tablesText(detail, res.table_ids || [res.table_id])),
          h("dt", {}, "When"), h("dd", {}, prettyWhen(res.starts_at_local)),
          h("dt", {}, "Guests"), h("dd", {}, String(res.party_size))),
        cancel));
      if (errMsg) out.appendChild(h("p", { class: "notice notice-error", testid: "reservation-error", role: "alert" }, errMsg));
    }

    main.appendChild(h("h1", {}, "Find your booking"));
    main.appendChild(h("p", { class: "lede" }, "Enter the reference from your confirmation to view or cancel it."));
    main.appendChild(h("section", { class: "card narrow" }, h("form", { class: "stack", onsubmit: function (ev) {
      ev.preventDefault();
      var ref = input.value.trim().toUpperCase();
      if (!ref) { showError("Enter your booking reference."); return; }
      lookup(ref);
    } },
      h("div", { class: "field" }, h("label", { for: "lookup-reference-input" }, "Booking reference"), input),
      h("button", { class: "btn btn-primary", type: "submit", testid: "lookup-submit" }, "Look up"))));
    main.appendChild(out);
  }

  render();
})();
