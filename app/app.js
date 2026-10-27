// Replaces the native city select and date inputs with a searchable city
// list and a calendar. The native controls stay in the form and hold the
// values, so the page still works without JavaScript.
(function () {
  "use strict";
  document.documentElement.classList.add("js");
  themeSwitch();
  const form = document.querySelector(".ask");
  if (!form) return;

  const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December"];
  const pad = (n) => String(n).padStart(2, "0");
  const iso = (d) => `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
  const parse = (s) => (s ? new Date(s + "T00:00:00Z") : null);
  const longDay = (d) => `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
  const plain = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const el = (tag, attrs = {}, text) => {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    if (text !== undefined) node.textContent = text;
    return node;
  };

  let openPop = null;
  function closePop() {
    if (!openPop) return;
    openPop.pop.hidden = true;
    openPop.trigger.setAttribute("aria-expanded", "false");
    openPop = null;
  }
  function showPop(trigger, pop, focus) {
    closePop();
    pop.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    openPop = { trigger, pop };
    // keep the popover on screen on narrow phones
    pop.style.left = "0px";
    const r = pop.getBoundingClientRect();
    if (r.right > window.innerWidth - 12) pop.style.left = `${window.innerWidth - 12 - r.right}px`;
    if (focus) focus.focus();
  }
  // pointerdown, not click: a click inside the calendar redraws it, and by the
  // time the click event arrives its target is no longer in the page
  document.addEventListener("pointerdown", (e) => {
    if (openPop && !openPop.pop.contains(e.target) && !openPop.trigger.contains(e.target)) closePop();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && openPop) {
      const t = openPop.trigger;
      closePop();
      t.focus();
    }
  });
  const submit = () => form.requestSubmit ? form.requestSubmit() : form.submit();
  // leave an empty second date out of the address
  form.addEventListener("submit", () => {
    form.querySelectorAll("input").forEach((input) => { if (!input.value) input.disabled = true; });
  });

  // ---------------------------------------------------------------- city
  function cityField(field) {
    const select = field.querySelector("select");
    const cities = [...select.options].map((o) => ({
      id: o.value, name: o.textContent, revisions: Number(o.dataset.revisions), first: o.dataset.first,
    }));
    const current = cities.find((c) => c.id === select.value);

    const trigger = el("button", { type: "button", class: "pick", "aria-haspopup": "listbox", "aria-expanded": "false" });
    trigger.append(current.name, el("span", { class: "caret", "aria-hidden": "true" }));
    const pop = el("div", { class: "pop", hidden: "" });
    const search = el("input", {
      class: "search", type: "search", placeholder: "Search 45 cities", autocomplete: "off",
      role: "combobox", "aria-expanded": "true", "aria-controls": "city-list", "aria-label": "Search cities",
    });
    const list = el("ul", { class: "list", id: "city-list", role: "listbox", "aria-label": "Cities" });
    pop.append(search, list);
    field.append(trigger, pop);

    let shown = [];
    let active = 0;

    function render() {
      const q = plain(search.value.trim());
      shown = cities
        .filter((c) => plain(c.name).includes(q))
        .sort((a, b) => (q ? plain(a.name).indexOf(q) - plain(b.name).indexOf(q) : 0));
      list.replaceChildren();
      if (!shown.length) {
        list.append(el("li", { class: "none" }, "No city with that name. Try another spelling."));
        return;
      }
      active = Math.min(active, shown.length - 1);
      shown.forEach((c, i) => {
        const li = el("li", { role: "option", id: `city-${c.id}`, "aria-selected": String(i === active) });
        if (c.id === select.value) li.classList.add("current");
        const name = el("span");
        const at = q ? plain(c.name).indexOf(q) : -1;
        if (at >= 0) {
          name.append(c.name.slice(0, at), el("mark", {}, c.name.slice(at, at + q.length)), c.name.slice(at + q.length));
        } else {
          name.textContent = c.name;
        }
        li.append(name, el("small", {}, `${c.revisions.toLocaleString("en")} edits`));
        li.addEventListener("mousedown", (e) => { e.preventDefault(); choose(c); });
        li.addEventListener("mousemove", () => { if (active !== i) { active = i; mark(); } });
        list.append(li);
      });
      search.setAttribute("aria-activedescendant", `city-${shown[active].id}`);
    }
    function mark() {
      [...list.children].forEach((li, i) => li.setAttribute("aria-selected", String(i === active)));
      const li = list.children[active];
      if (li) {
        li.scrollIntoView({ block: "nearest" });
        search.setAttribute("aria-activedescendant", li.id);
      }
    }
    function choose(c) {
      select.value = c.id;
      closePop();
      trigger.firstChild.textContent = c.name;
      submit();
    }
    trigger.addEventListener("click", () => {
      if (openPop && openPop.pop === pop) return closePop();
      search.value = "";
      active = Math.max(0, cities.findIndex((c) => c.id === select.value));
      render();
      showPop(trigger, pop, search);
      mark();
    });
    search.addEventListener("input", () => { active = 0; render(); });
    search.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { active = Math.min(active + 1, shown.length - 1); mark(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { active = Math.max(active - 1, 0); mark(); e.preventDefault(); }
      else if (e.key === "Enter") { e.preventDefault(); if (shown[active]) choose(shown[active]); }
    });
    return current;
  }

  // ---------------------------------------------------------------- dates
  function dateField(field, city) {
    const input = field.querySelector("input");
    const optional = field.hasAttribute("data-optional");
    const min = parse(input.min);
    const max = parse(input.max);
    let value = parse(input.value);
    let view = "days";
    let cursor = new Date(value || max);

    const trigger = el("button", { type: "button", class: "pick", "aria-haspopup": "dialog", "aria-expanded": "false" });
    const pop = el("div", { class: "pop", hidden: "", role: "dialog", "aria-label": optional ? "Pick a second date" : "Pick a date" });
    field.append(trigger, pop);
    if (optional && value) {
      const clear = el("button", { type: "button", class: "clear" }, "remove");
      clear.addEventListener("click", () => { input.value = ""; submit(); });
      field.append(clear);
    }

    function label() {
      trigger.replaceChildren(value ? longDay(value) : "a second date", el("span", { class: "caret", "aria-hidden": "true" }));
      trigger.classList.toggle("unset", !value);
    }
    const inRange = (d) => d >= min && d <= max;
    function choose(d) {
      value = d;
      input.value = iso(d);
      label();
      closePop();
      submit();
    }

    const minY = min.getUTCFullYear();
    const maxY = max.getUTCFullYear();
    const button = (text, cls, onClick, extra = {}) => {
      const b = el("button", { type: "button", class: cls, ...extra }, text);
      b.addEventListener("click", (e) => { e.stopPropagation(); onClick(); });
      return b;
    };
    // keep the cursor inside the allowed months
    const clamp = (d) => (d < new Date(Date.UTC(minY, min.getUTCMonth(), 1)) ? new Date(Date.UTC(minY, min.getUTCMonth(), 1))
      : d > max ? new Date(Date.UTC(maxY, max.getUTCMonth(), 1)) : d);

    // header: previous, month menu, year menu, next
    function head(stepBy) {
      const y = cursor.getUTCFullYear();
      const m = cursor.getUTCMonth();
      const h = el("div", { class: "cal-head" });
      const prev = button("‹", "nav", () => { cursor = clamp(stepBy(-1)); draw(); }, { "aria-label": "Earlier" });
      const next = button("›", "nav", () => { cursor = clamp(stepBy(1)); draw(); }, { "aria-label": "Later" });
      const month = button(MONTHS[m], `menu${view === "months" ? " open" : ""}`,
        () => { view = view === "months" ? "days" : "months"; draw(); }, { "aria-label": "Choose the month" });
      const year = button(String(y), `menu${view === "years" ? " open" : ""}`,
        () => { view = view === "years" ? "days" : "years"; draw(); }, { "aria-label": "Choose the year" });
      month.append(el("span", { class: "caret", "aria-hidden": "true" }));
      year.append(el("span", { class: "caret", "aria-hidden": "true" }));
      const menus = el("div", { class: "menus" });
      menus.append(month, year);
      h.append(prev, menus, next);
      return { h, prev, next };
    }

    function draw() {
      pop.replaceChildren();
      const y = cursor.getUTCFullYear();
      const m = cursor.getUTCMonth();
      if (view === "years") {
        const { h, prev, next } = head((dir) => new Date(Date.UTC(y + dir, m, 1)));
        prev.disabled = y <= minY;
        next.disabled = y >= maxY;
        const grid = el("div", { class: "cal-grid years" });
        for (let yy = minY; yy <= maxY; yy++) {
          const b = button(String(yy), yy === y ? "chosen" : "", () => {
            cursor = clamp(new Date(Date.UTC(yy, m, 1)));
            view = "days";
            draw();
          });
          grid.append(b);
        }
        pop.append(h, grid);
      } else if (view === "months") {
        const { h, prev, next } = head((dir) => new Date(Date.UTC(y + dir, m, 1)));
        prev.disabled = y <= minY;
        next.disabled = y >= maxY;
        const grid = el("div", { class: "cal-grid months" });
        MONTHS.forEach((name, mm) => {
          const b = button(name.slice(0, 3), mm === m ? "chosen" : "", () => {
            cursor = new Date(Date.UTC(y, mm, 1));
            view = "days";
            draw();
          });
          b.disabled = new Date(Date.UTC(y, mm + 1, 0)) < min || new Date(Date.UTC(y, mm, 1)) > max;
          grid.append(b);
        });
        pop.append(h, grid);
      } else {
        const { h, prev, next } = head((dir) => new Date(Date.UTC(y, m + dir, 1)));
        prev.disabled = new Date(Date.UTC(y, m, 0)) < min;
        next.disabled = new Date(Date.UTC(y, m + 1, 1)) > max;
        const grid = el("div", { class: "cal-grid", role: "grid" });
        ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"].forEach((d) => grid.append(el("span", { class: "dow" }, d)));
        const first = new Date(Date.UTC(y, m, 1));
        for (let i = 0; i < (first.getUTCDay() + 6) % 7; i++) grid.append(el("span"));
        const days = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
        for (let d = 1; d <= days; d++) {
          const day = new Date(Date.UTC(y, m, d));
          const b = button(String(d), "", () => choose(day), { "aria-label": longDay(day) });
          b.disabled = !inRange(day);
          if (value && iso(day) === iso(value)) b.classList.add("chosen");
          if (iso(day) === iso(max)) b.classList.add("today");
          grid.append(b);
        }
        pop.append(h, grid);
      }
      const foot = el("div", { class: "cal-foot" });
      const shortcut = (text, d) => foot.append(button(text, "", () => choose(d)));
      if (city && city.first) shortcut(`First edit of ${city.name}`, parse(city.first));
      for (const yy of [2005, 2010, 2015, 2020]) shortcut(`1 Jan ${yy}`, new Date(Date.UTC(yy, 0, 1)));
      shortcut("Today", max);
      pop.append(foot);
    }

    trigger.addEventListener("click", () => {
      if (openPop && openPop.pop === pop) return closePop();
      view = "days";
      cursor = new Date(value || max);
      draw();
      showPop(trigger, pop, pop.querySelector(".chosen") || pop.querySelector(".cal-grid button:not(:disabled)"));
    });
    label();
  }

  let city = null;
  form.querySelectorAll(".field").forEach((field) => {
    if (field.dataset.kind === "city") city = cityField(field);
  });
  form.querySelectorAll('.field[data-kind="date"]').forEach((field) => dateField(field, city));

  // The switch in the corner. Without a saved choice the page follows the
  // system theme; a click saves the choice for next time.
  function themeSwitch() {
    const root = document.documentElement;
    const button = document.querySelector(".theme");
    if (!button) return;
    const system = matchMedia("(prefers-color-scheme: dark)");
    const show = () => {
      const dark = root.dataset.mode === "dark";
      button.setAttribute("aria-pressed", String(dark));
      button.querySelector("span").textContent = dark ? "Light" : "Dark";
      button.title = dark ? "Switch to light mode" : "Switch to dark mode";
    };
    button.addEventListener("click", () => {
      const next = root.dataset.mode === "dark" ? "light" : "dark";
      root.dataset.theme = root.dataset.mode = next;
      try { localStorage.setItem("theme", next); } catch (e) {}
      show();
    });
    system.addEventListener("change", () => {
      if (root.dataset.theme) return;
      root.dataset.mode = system.matches ? "dark" : "light";
      show();
    });
    show();
  }
})();
