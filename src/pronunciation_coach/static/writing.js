"use strict";
// Writing tab: tasks + editor, LLM correction, grammar lessons, progress.
// Uses the helpers from app.js ($, el, api, setStatus, showTab).

const W = {
  meta: null,            // /api/writing/tasks payload
  lessons: null,         // /api/writing/lessons payload
  lessonsById: new Map(),
  task: null,            // selected task
  result: null,          // last correction shown
  selectedErr: null,
  version: "corrected",  // "corrected" | "upgraded"
  view: "write",
  lessonId: null,
  timer: { running: false, left: 0, handle: null },
  startedAt: null,       // first keystroke for this draft (seconds_spent)
  busy: false,
  loading: null,
};

const W_STORE = {
  get(key, fallback = null) { try { const v = localStorage.getItem(`pc.writing.${key}`); return v == null ? fallback : JSON.parse(v); } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem(`pc.writing.${key}`, JSON.stringify(value)); } catch {} },
  del(key) { try { localStorage.removeItem(`pc.writing.${key}`); } catch {} },
};

const taskKey = (t) => t ? (t.id || `gen:${t.title}`) : "free";
const wordCount = (text) => (text.match(/[A-Za-zÀ-ÿ0-9]+(?:['’\-][A-Za-zÀ-ÿ0-9]+)*/g) || []).length;
const fmtTime = (s) => `${s < 0 ? "−" : ""}${Math.floor(Math.abs(s) / 60)}:${String(Math.abs(s) % 60).padStart(2, "0")}`;
const scoreClass = (v) => v >= 70 ? "good" : v >= 55 ? "unsure" : "bad";

function loadWritingMeta() {
  if (!W.loading) {
    W.loading = Promise.all([api("/api/writing/tasks"), api("/api/writing/lessons")]).then(([meta, lessons]) => {
      W.meta = meta;
      W.lessons = lessons;
      for (const l of lessons.lessons) W.lessonsById.set(l.id, l);
      $("w-count-lessons").textContent = lessons.lessons.length;
      fillSelects();
    }).catch((err) => { W.loading = null; throw err; });
  }
  return W.loading;
}

function fillSelects() {
  const filter = $("w-exam-filter");
  const gen = $("w-gen-exam");
  const genre = $("w-gen-genre");
  filter.replaceChildren(el("option", { value: "" }, "All tasks"));
  gen.replaceChildren();
  for (const x of W.meta.exams) {
    filter.append(el("option", { value: x.id }, x.label));
    gen.append(el("option", { value: x.id }, x.label));
  }
  genre.replaceChildren(el("option", { value: "" }, "Any"));
  for (const g of W.meta.genres) genre.append(el("option", { value: g.id }, g.label));
  filter.value = W_STORE.get("filter", "") || "";
}

// --------------------------------------------------------------------- views
function setWritingView(view) {
  W.view = view;
  document.querySelectorAll("#w-views [data-view]").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.view === view)));
  for (const v of ["write", "lessons", "progress"]) $(`w-view-${v}`).classList.toggle("hidden", v !== view);
  if (view === "lessons") renderLessons();
  if (view === "progress") renderProgress();
}
document.querySelectorAll("#w-views [data-view]").forEach((b) =>
  b.addEventListener("click", () => setWritingView(b.dataset.view)));

async function renderWriting() {
  try { await loadWritingMeta(); } catch (err) { setStatus(`Error: ${err.message}`); return; }
  if (!W.task) {
    const saved = W_STORE.get("task");
    W.task = (saved && saved.id && W.meta.tasks.find((t) => t.id === saved.id)) || saved || W.meta.tasks[0];
    selectTask(W.task, { keepResult: false });
  }
  renderTaskList();
  updateSubCount();
  setWritingView(W.view);
}

async function updateSubCount() {
  try {
    const { submissions } = await api("/api/writing/submissions");
    $("w-count-subs").textContent = submissions.length || "";
  } catch {}
}

// --------------------------------------------------------------------- tasks
function generatedTasks() { return W_STORE.get("generated", []) || []; }

function renderTaskList() {
  const list = $("w-task-list");
  const filter = $("w-exam-filter").value;
  const items = [...generatedTasks(), ...W.meta.tasks].filter((t) => !filter || t.exam === filter);
  list.replaceChildren(...items.map((t) => {
    const active = taskKey(t) === taskKey(W.task);
    const btn = el("button", {
      type: "button", class: `w-task-item${active ? " active" : ""}`, "aria-current": active ? "true" : "false",
      onclick: () => selectTask(t),
    },
    el("span", { class: "w-task-item-title" }, t.title),
    el("span", { class: "w-task-item-meta" },
      t.generated ? el("span", { class: "w-new" }, "Generated") : "",
      `${t.exam_label} · ${t.words[0]}–${t.words[1]} words`));
    return el("li", {}, btn);
  }));
  if (!items.length) list.append(el("li", { class: "muted" }, "No tasks for this exam."));
}

$("w-exam-filter").addEventListener("change", () => { W_STORE.set("filter", $("w-exam-filter").value); renderTaskList(); });

function selectTask(t, { keepResult = false } = {}) {
  if (W.task && $("w-text").value.trim()) W_STORE.set(`draft.${taskKey(W.task)}`, $("w-text").value);
  W.task = t;
  W_STORE.set("task", t.id ? { id: t.id } : t);
  stopTimer(true);
  const draft = W_STORE.get(`draft.${taskKey(t)}`, "");
  $("w-text").value = draft || "";
  W.startedAt = null;
  if (!keepResult) { W.result = null; renderWritingResult(); }
  renderTask();
  renderTaskList();
  updateCount();
  hideWError();
}

function renderTask() {
  const t = W.task;
  const box = $("w-task");
  box.replaceChildren(
    el("p", { class: "w-task-meta" },
      el("span", {}, t.exam_label), el("span", {}, t.genre_label),
      t.register ? el("span", {}, t.register) : "",
      el("span", {}, `${t.words[0]}–${t.words[1]} words`), el("span", {}, `${t.minutes} min`)),
    el("h3", { class: "w-task-title" }, t.title),
    el("p", { class: "w-task-prompt" }, t.prompt),
    t.points && t.points.length
      ? el("ul", { class: "w-points" }, ...t.points.map((p) => el("li", {}, p))) : "",
  );
  $("w-timer").replaceChildren(clockIcon(), el("span", { id: "w-timer-l" }, `Timer ${t.minutes} min`));
}

function clockIcon() {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", "icon");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", "M8 1.5a6.5 6.5 0 1 1 0 13 6.5 6.5 0 0 1 0-13zm0 1.3a5.2 5.2 0 1 0 0 10.4A5.2 5.2 0 0 0 8 2.8zm.6 1.9v3.05l2.1 1.25a.6.6 0 1 1-.6 1.03L7.7 8.6a.6.6 0 0 1-.3-.52V4.7a.6.6 0 1 1 1.2 0z");
  svg.append(path);
  return svg;
}

$("w-gen-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("w-gen-btn");
  btn.disabled = true;
  btn.textContent = "Generating…";
  $("w-gen-msg").textContent = "";
  try {
    const t = await api("/api/writing/tasks/generate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ exam: $("w-gen-exam").value || null, genre: $("w-gen-genre").value || null,
                             topic: $("w-gen-topic").value.trim() || null }),
    });
    const list = [t, ...generatedTasks().filter((x) => x.title !== t.title)].slice(0, 10);
    W_STORE.set("generated", list);
    $("w-exam-filter").value = "";
    selectTask(t);
    $("w-gen-topic").value = "";
  } catch (err) {
    $("w-gen-msg").textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate";
  }
});

// -------------------------------------------------------------------- editor
function updateCount() {
  const n = wordCount($("w-text").value);
  const [lo, hi] = W.task ? W.task.words : [0, 0];
  const max = Math.max(hi * 1.25, 1);
  $("w-count-n").textContent = n;
  const state = n === 0 ? "" : n < lo ? "under" : n > hi ? "over" : "ok";
  $("w-count").dataset.state = state;
  $("w-count-l").textContent = `/ ${lo}–${hi} words` + (state === "under" ? ` · ${lo - n} to go` : state === "over" ? " · over the limit" : "");
  $("w-meter-fill").style.width = `${Math.min(100, (n / max) * 100)}%`;
  $("w-meter-lo").style.left = `${(lo / max) * 100}%`;
  $("w-meter-hi").style.left = `${(hi / max) * 100}%`;
}

let draftTimer = null;
$("w-text").addEventListener("input", () => {
  if (W.startedAt == null) W.startedAt = Date.now();
  updateCount();
  clearTimeout(draftTimer);
  draftTimer = setTimeout(() => W_STORE.set(`draft.${taskKey(W.task)}`, $("w-text").value), 400);
});

function tickTimer() {
  W.timer.left -= 1;
  const l = $("w-timer-l");
  if (l) l.textContent = W.timer.left >= 0 ? `${fmtTime(W.timer.left)} left` : `Time's up · ${fmtTime(-W.timer.left)} over`;
  $("w-timer").classList.toggle("over", W.timer.left < 0);
}

function stopTimer(reset = false) {
  clearInterval(W.timer.handle);
  W.timer.running = false;
  W.timer.handle = null;
  $("w-timer").setAttribute("aria-pressed", "false");
  $("w-timer").classList.remove("running", "over");
  if (reset && W.task) {
    const l = $("w-timer-l");
    if (l) l.textContent = `Timer ${W.task.minutes} min`;
  }
}

$("w-timer").addEventListener("click", () => {
  if (W.timer.running) { stopTimer(true); return; }
  W.timer.left = W.task.minutes * 60 + 1;
  W.timer.running = true;
  $("w-timer").setAttribute("aria-pressed", "true");
  $("w-timer").classList.add("running");
  $("w-timer").title = "Stop the timer";
  tickTimer();
  W.timer.handle = setInterval(tickTimer, 1000);
  $("w-text").focus();
});

function showWError(msg) { const e = $("w-error"); e.textContent = msg; e.classList.remove("hidden"); }
function hideWError() { $("w-error").classList.add("hidden"); }

async function submitWriting() {
  if (W.busy) return;
  const text = $("w-text").value;
  if (wordCount(text) < 10) { showWError("Write at least 10 words before checking."); return; }
  W.busy = true;
  hideWError();
  const btn = $("w-submit");
  btn.disabled = true;
  btn.classList.add("loading");
  btn.textContent = "Checking…";
  setStatus("Checking your writing (usually 5–20 s)…");
  try {
    const seconds = W.startedAt ? Math.round((Date.now() - W.startedAt) / 1000) : null;
    W.result = await api("/api/writing/correct", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, task: W.task, seconds_spent: seconds }),
    });
    W.selectedErr = null;
    W.version = "corrected";
    stopTimer(true);
    renderWritingResult();
    updateSubCount();
    setStatus("");
    $("w-result").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    showWError(err.message);
    setStatus("");
  } finally {
    W.busy = false;
    btn.disabled = false;
    btn.classList.remove("loading");
    btn.textContent = "Check my writing";
  }
}
$("w-submit").addEventListener("click", submitWriting);
$("w-text").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); submitWriting(); }
});

// -------------------------------------------------------------------- result
function lessonLink(lessonId, label) {
  if (!lessonId) return "";
  const lesson = W.lessonsById.get(lessonId);
  return el("a", {
    href: "#", class: "w-lesson-link",
    onclick: (e) => { e.preventDefault(); openLesson(lessonId); },
  }, label || `Lesson: ${lesson ? lesson.title : lessonId}`, " →");
}

function criterionBar(key, label, value) {
  return el("div", { class: "w-crit" },
    el("div", { class: "w-crit-head" }, el("span", {}, label), el("b", { class: scoreClass(value) }, String(value))),
    el("div", { class: "w-crit-bar", role: "img", "aria-label": `${label}: ${value} of 100` },
      Object.assign(el("span", { class: scoreClass(value) }), { style: `width:${value}%` })));
}

function annotatedText(r) {
  const box = el("div", { class: "w-annotated", lang: "en" });
  let pos = 0;
  for (const e of r.errors) {
    if (e.start < pos) continue;
    box.append(r.text.slice(pos, e.start));
    // A span (not a <button>) so long marks wrap across lines like the surrounding text.
    const mark = el("span", {
      role: "button", tabindex: "0", class: `w-err${W.selectedErr === e.id ? " selected" : ""}`, "data-err": e.id,
      title: `${e.category_label}: ${e.original} → ${e.correction}`,
      "aria-label": `Error: ${e.original}. Correction: ${e.correction}. ${e.category_label}`,
      onclick: (ev) => { ev.stopPropagation(); selectError(e.id); },
      onkeydown: (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); selectError(e.id); } },
    }, el("s", {}, r.text.slice(e.start, e.end)), el("span", { class: "w-fix" }, e.correction));
    box.append(mark);
    pos = e.end;
  }
  box.append(r.text.slice(pos));
  return box;
}

function errorDetail(e) {
  if (!e) {
    return el("div", { class: "w-detail w-detail-empty" },
      W.result.errors.length ? "Click a highlighted mistake to see the rule." : "No mistakes found to highlight.");
  }
  return el("div", { class: "w-detail", "aria-live": "polite" },
    el("div", { class: "w-detail-head" },
      el("span", { class: "w-cat" }, e.category_label),
      el("span", { class: "w-detail-change" }, el("s", {}, e.original), " → ", el("b", {}, e.correction))),
    el("p", { class: "w-detail-rule", lang: "es" }, e.explanation),
    e.example ? el("p", { class: "w-detail-ex" }, el("span", { class: "label" }, "Example"), el("i", { lang: "en" }, e.example)) : "",
    lessonLink(e.lesson_id));
}

function selectError(id) {
  W.selectedErr = W.selectedErr === id ? null : id;
  document.querySelectorAll(".w-err").forEach((n) => n.classList.toggle("selected", Number(n.dataset.err) === W.selectedErr));
  const e = [...W.result.errors, ...W.result.unlocated].find((x) => x.id === W.selectedErr);
  $("w-detail-slot").replaceChildren(errorDetail(e));
}

function categoryChips(r) {
  const counts = new Map();
  for (const e of [...r.errors, ...r.unlocated]) counts.set(e.category_label, (counts.get(e.category_label) || 0) + 1);
  return el("div", { class: "w-chips" }, ...[...counts.entries()].sort((a, b) => b[1] - a[1])
    .map(([label, n]) => el("span", { class: "w-chip" }, label, el("span", { class: "seg-count" }, String(n)))));
}

function renderWritingResult() {
  const box = $("w-result");
  const r = W.result;
  box.classList.toggle("hidden", !r);
  if (!r) { box.replaceChildren(); return; }
  const crit = r.criteria || (W.meta && W.meta.criteria) || {};
  const nErr = r.errors.length + r.unlocated.length;

  const versions = el("div", { class: "w-versions" });
  const renderVersion = () => {
    const text = W.version === "upgraded" ? r.upgraded_text : r.corrected_text;
    versions.replaceChildren(
      el("div", { class: "w-versions-head" },
        el("div", { class: "seg", role: "group", "aria-label": "Version" },
          ...[["corrected", "Corrected"], ["upgraded", "Upgraded to B2/C1"]].map(([v, label]) => el("button", {
            type: "button", "aria-pressed": String(W.version === v),
            onclick: () => { W.version = v; renderVersion(); },
          }, label))),
        el("button", {
          type: "button", class: "ghost play small", onclick: async (ev) => {
            try { await navigator.clipboard.writeText(text); ev.target.textContent = "Copied"; }
            catch { ev.target.textContent = "Copy failed"; }
            setTimeout(() => { ev.target.textContent = "Copy"; }, 1500);
          },
        }, "Copy")),
      el("p", { class: "w-version-note" }, W.version === "upgraded"
        ? "Same ideas with richer vocabulary and linking words. Compare it with yours and borrow phrases."
        : "Your text with only the mistakes fixed."),
      el("div", { class: "w-version-text", lang: "en" }, text));
  };
  renderVersion();

  box.replaceChildren(
    el("div", { class: "w-score-row" },
      el("div", { class: `score ${scoreClass(r.overall)}` }, el("small", {}, "Overall"), String(r.overall)),
      el("div", { class: "w-estimates" },
        el("div", {}, el("span", { class: "label" }, "Level"), el("b", { class: "w-level" }, r.cefr_estimate),
          el("span", { class: "muted" }, ` · IELTS ≈ ${r.ielts_band_estimate.toFixed(1)}`)),
        el("div", { class: "w-estimate-note" }, "Estimates from an AI examiner, not an official score."),
        el("div", { class: "w-estimate-note" }, `${r.word_count} words · ${nErr} ${nErr === 1 ? "mistake" : "mistakes"} · ${r.model}`)),
      el("div", { class: "w-crits" }, ...Object.entries(crit).map(([k, label]) => criterionBar(k, label, r.scores[k])))),
    r.summary ? el("p", { class: "w-summary", lang: "es" }, r.summary) : "",
    el("h2", {}, "Your text"),
    nErr ? categoryChips(r) : "",
    annotatedText(r),
    el("div", { id: "w-detail-slot" }, errorDetail(null)),
    r.unlocated.length ? el("div", { class: "w-unlocated" },
      el("h2", {}, "Other notes"),
      el("p", { class: "muted w-unlocated-note" }, "These could not be matched to an exact place in your text."),
      el("ul", { class: "errors" }, ...r.unlocated.map((e) => el("li", {},
        el("div", { class: "msg" }, el("span", { class: "w-cat" }, e.category_label), " ",
          el("s", {}, e.original), " → ", el("b", {}, e.correction)),
        el("div", { class: "tip", lang: "es" }, e.explanation),
        lessonLink(e.lesson_id))))) : "",
    r.priorities.length ? el("div", {},
      el("h2", {}, "Work on next"),
      el("ol", { class: "w-priorities" }, ...r.priorities.map((p) => el("li", {},
        el("div", { class: "msg", lang: "es" }, p.title),
        el("div", { class: "tip", lang: "es" }, p.detail),
        lessonLink(p.lesson_id))))) : "",
    el("h2", {}, "Improved versions"),
    versions,
  );
}

// ------------------------------------------------------------------- lessons
async function openLesson(id) {
  if (!$("tab-writing").classList.contains("active")) showTab("writing");
  await loadWritingMeta().catch(() => {});
  W.lessonId = id;
  setWritingView("lessons");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderLessons() {
  if (!W.lessons) return;
  const suggested = new Set(W_STORE.get("suggested", []) || []);
  if (!W.lessonId) W.lessonId = W.lessons.lessons[0].id;
  $("w-lesson-list").replaceChildren(...W.lessons.lessons.map((l) => {
    const active = l.id === W.lessonId;
    const done = W_STORE.get(`lesson.${l.id}`);
    return el("li", {}, el("button", {
      type: "button", class: `w-task-item${active ? " active" : ""}`, "aria-current": active ? "true" : "false",
      onclick: () => { W.lessonId = l.id; renderLessons(); },
    }, el("span", { class: "w-task-item-title" }, l.title),
    el("span", { class: "w-task-item-meta" },
      suggested.has(l.id) ? el("span", { class: "w-new" }, "Review") : "",
      done ? `Best ${done.score}/${done.total}` : l.category_labels.join(" · "))));
  }));
  renderLesson(W.lessonsById.get(W.lessonId));
}

function renderLesson(l) {
  const box = $("w-lesson");
  const inputs = l.exercise.map((item, i) => el("input", {
    type: "text", class: "w-ex-input", autocomplete: "off", spellcheck: "false", "aria-label": `Answer ${i + 1}`,
    placeholder: item.kind === "fill" ? "missing word(s)" : "rewrite the sentence correctly",
  }));
  const feedback = l.exercise.map(() => el("div", { class: "w-ex-feedback", "aria-live": "polite" }));
  const score = el("span", { class: "w-ex-score", "aria-live": "polite" });
  const form = el("form", { class: "w-ex" },
    el("ol", { class: "w-ex-list" }, ...l.exercise.map((item, i) => el("li", { class: "w-ex-item" },
      el("p", { class: "w-ex-prompt", lang: "en" },
        el("span", { class: "w-ex-kind" }, item.kind === "fill" ? "Fill in" : "Fix it"),
        ...(item.kind === "fill"
          ? item.prompt.split("___").flatMap((part, j) => j ? [el("span", { class: "w-blank" }, "____"), part] : [part])
          : [item.prompt])),
      inputs[i], feedback[i]))),
    el("div", { class: "w-ex-bar" },
      el("button", { type: "submit", class: "primary" }, "Check answers"),
      el("button", { type: "button", class: "ghost", onclick: () => {
        inputs.forEach((x) => { x.value = ""; x.classList.remove("right", "wrong"); });
        feedback.forEach((f) => f.replaceChildren());
        score.textContent = "";
      } }, "Clear"),
      score));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const res = await api(`/api/writing/lessons/${encodeURIComponent(l.id)}/check`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answers: inputs.map((x) => x.value) }),
      });
      res.results.forEach((r, i) => {
        inputs[i].classList.toggle("right", r.correct);
        inputs[i].classList.toggle("wrong", !r.correct);
        feedback[i].replaceChildren(r.correct
          ? el("span", { class: "w-ok" }, "Correct. ", el("span", { lang: "es" }, r.explanation))
          : el("span", { class: "w-no" }, "Answer: ", el("b", { lang: "en" }, r.answer.replace(/[.!?]$/, "")), ". ", el("span", { lang: "es" }, r.explanation)));
      });
      score.textContent = `${res.score} / ${res.total} correct`;
      const best = W_STORE.get(`lesson.${l.id}`);
      if (!best || res.score > best.score) W_STORE.set(`lesson.${l.id}`, { score: res.score, total: res.total });
    } catch (err) {
      score.textContent = `Error: ${err.message}`;
    }
  });

  box.replaceChildren(
    el("header", { class: "w-lesson-head" },
      el("h3", { class: "w-lesson-title" }, l.title),
      el("div", { class: "w-chips" }, ...l.category_labels.map((c) => el("span", { class: "w-chip" }, c)))),
    el("p", { class: "w-lesson-summary", lang: "es" }, l.summary),
    el("p", { class: "w-lesson-text", lang: "es" }, l.explanation),
    el("table", { class: "w-pairs" },
      el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Wrong"), el("th", { scope: "col" }, "Right"))),
      el("tbody", {}, ...l.examples.map((x) => el("tr", {},
        el("td", { class: "w-wrong", lang: "en" }, x.wrong), el("td", { class: "w-right", lang: "en" }, x.right))))),
    el("h2", { class: "w-ex-title" }, "Practice"),
    form,
  );
}

// ------------------------------------------------------------------ progress
const SERIES = [
  ["overall", "Overall"], ["task_achievement", "Task"], ["coherence_cohesion", "Coherence"],
  ["grammar", "Grammar"], ["vocabulary", "Vocabulary"],
];

function scoreChart(points) {
  const box = $("w-chart");
  if (!points.length) { box.textContent = "No corrected texts yet."; $("w-legend").replaceChildren(); return; }
  const W_ = 600, H = 220, P = { l: 30, r: 12, t: 12, b: 28 };
  const x = (i) => P.l + (points.length === 1 ? (W_ - P.l - P.r) / 2 : (i * (W_ - P.l - P.r)) / (points.length - 1));
  const y = (v) => P.t + (1 - v / 100) * (H - P.t - P.b);
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W_} ${H}`);
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Writing scores per submission");
  const add = (tag, attrs, text) => {
    const n = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text != null) n.textContent = text;
    svg.append(n);
    return n;
  };
  for (const [v, label] of [[0, "0"], [55, "B1"], [70, "B2"], [85, "C1"], [100, "100"]]) {
    add("line", { x1: P.l, x2: W_ - P.r, y1: y(v), y2: y(v), class: `axis${v === 70 ? " target" : ""}` });
    add("text", { x: 2, y: y(v) + 4 }, label);
  }
  SERIES.forEach(([key], si) => {
    add("polyline", { class: `wline s${si}`, points: points.map((p, i) => `${x(i)},${y(p[key])}`).join(" ") });
  });
  points.forEach((p, i) => {
    add("circle", { cx: x(i), cy: y(p.overall), r: 4, class: "pt" })
      .append(Object.assign(document.createElementNS(SVG_NS, "title"),
        { textContent: `${new Date(p.created_at).toLocaleDateString()} · ${p.task_title || "Free writing"}: ${p.overall} (${p.cefr_estimate})` }));
  });
  const step = Math.max(1, Math.ceil(points.length / 6));
  points.forEach((p, i) => {
    if (i % step === 0) add("text", { x: x(i) - 14, y: H - 8 }, new Date(p.created_at).toLocaleDateString(undefined, { month: "2-digit", day: "2-digit" }));
  });
  box.replaceChildren(svg);
  $("w-legend").replaceChildren(...SERIES.map(([, label], si) =>
    el("span", { class: "w-legend-item" }, el("span", { class: `w-swatch s${si}` }), label)),
    el("span", { class: "w-legend-item muted" }, "Dashed line: B2 (70)"));
}

async function renderProgress() {
  let s, subs;
  try {
    [s, { submissions: subs }] = await Promise.all([api("/api/writing/stats"), api("/api/writing/submissions")]);
  } catch (err) { setStatus(`Error: ${err.message}`); return; }
  W_STORE.set("suggested", s.suggested_lessons.map((x) => x.lesson_id));
  const last = s.timeline[s.timeline.length - 1];
  const recent = s.timeline.slice(-5);
  const recentAvg = recent.length ? Math.round(recent.reduce((a, p) => a + p.overall, 0) / recent.length) : null;
  $("w-kpis").replaceChildren(...[
    ["Texts corrected", s.overall.submissions],
    ["Average score", s.overall.avg_overall == null ? "–" : Math.round(s.overall.avg_overall)],
    ["Last 5 texts", recentAvg ?? "–"],
    ["Latest level (estimate)", last ? last.cefr_estimate : "–"],
    ["Words written", s.overall.words || 0],
  ].map(([l, v]) => el("div", { class: "kpi" }, el("div", { class: "v" }, String(v)), el("div", { class: "l" }, l))));
  scoreChart(s.timeline);

  const top = $("w-top-cats");
  const maxCount = Math.max(1, ...s.categories.map((c) => c.count));
  top.replaceChildren(...s.categories.slice(0, 8).map((c) => el("li", {},
    el("span", { class: "count" }, `×${c.count}`),
    el("div", { class: "msg" }, c.label),
    el("div", { class: "w-cat-bar" }, Object.assign(el("span"), { style: `width:${(c.count / maxCount) * 100}%` })),
    c.examples.length ? el("div", { class: "tip", lang: "en" }, ...c.examples.flatMap((x, i) => [
      i ? " · " : "", el("s", {}, x.original), " → ", x.correction])) : "",
    lessonLink(c.lesson_id))));
  if (!s.categories.length) top.append(el("li", { class: "muted" }, "No mistakes recorded yet."));

  const sug = $("w-suggest");
  sug.replaceChildren(...s.suggested_lessons.map((x) => el("li", {},
    el("span", { class: "count" }, `×${x.count}`),
    el("div", { class: "msg" }, x.title),
    el("div", { class: "tip", lang: "es" }, x.summary),
    lessonLink(x.lesson_id, "Open lesson"))));
  if (!s.suggested_lessons.length) sug.append(el("li", { class: "muted" }, "Correct a text to get lesson suggestions based on your last 5 texts."));

  const table = $("w-history");
  table.replaceChildren(el("tr", {}, ...["Date", "Task", "Words", "Mistakes", "Score", "Level", ""].map((h) => el("th", {}, h))));
  for (const r of subs) {
    table.append(el("tr", {},
      el("td", {}, new Date(r.created_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })),
      el("td", {}, r.task_title || "Free writing"),
      el("td", { class: "num" }, String(r.word_count)),
      el("td", { class: "num" }, String(r.error_count)),
      el("td", { class: `num ${scoreClass(r.overall)}` }, String(r.overall)),
      el("td", {}, r.cefr_estimate || ""),
      el("td", { class: "w-row-actions" },
        el("button", { type: "button", class: "ghost play small", onclick: () => openSubmission(r.id) }, "Open"),
        el("button", { type: "button", class: "ghost play small", title: "Delete this text", onclick: async () => {
          if (!confirm("Delete this text and its correction?")) return;
          await api(`/api/writing/submissions/${r.id}`, { method: "DELETE" });
          renderProgress();
          updateSubCount();
        } }, "Delete"))));
  }
  if (!subs.length) table.append(el("tr", {}, el("td", { colspan: "7", class: "muted" }, "Your corrected texts will appear here.")));
}

async function openSubmission(id) {
  try {
    const sub = await api(`/api/writing/submissions/${id}`);
    const t = sub.task && sub.task.id ? (W.meta.tasks.find((x) => x.id === sub.task.id) || sub.task) : sub.task;
    if (t) {
      t.exam_label = t.exam_label || (W.meta.exams.find((x) => x.id === t.exam) || {}).label || "";
      t.genre_label = t.genre_label || (W.meta.genres.find((x) => x.id === t.genre) || {}).label || "";
      W.task = t;
      renderTask();
      renderTaskList();
    }
    $("w-text").value = sub.text;
    updateCount();
    W.result = sub;
    W.selectedErr = null;
    W.version = "corrected";
    setWritingView("write");
    renderWritingResult();
    $("w-result").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    setStatus(`Error: ${err.message}`);
  }
}

// --------------------------------------------------------------- stats card
async function renderStatsWriting() {
  const card = $("stats-writing");
  let s;
  try { s = await api("/api/writing/stats"); } catch { card.classList.add("hidden"); return; }
  if (!s.overall.submissions) { card.classList.add("hidden"); return; }
  const last = s.timeline[s.timeline.length - 1];
  const topCat = s.categories[0];
  card.classList.remove("hidden");
  card.replaceChildren(
    el("h2", {}, "Writing"),
    el("div", { class: "stats-writing-row" },
      ...[["Texts", s.overall.submissions], ["Average", Math.round(s.overall.avg_overall)],
          ["Latest level", last.cefr_estimate], ["Top mistake", topCat ? topCat.label : "–"]]
        .map(([l, v]) => el("div", {}, el("div", { class: "v" }, String(v)), el("div", { class: "l" }, l))),
      el("a", { href: "#writing", class: "w-lesson-link", onclick: (e) => {
        e.preventDefault(); W.view = "progress"; showTab("writing");
      } }, "Writing progress →")));
}
