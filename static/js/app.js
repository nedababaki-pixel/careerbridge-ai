// CareerBridge AI – browser logic. All AI output is inserted with textContent (never innerHTML).
(() => {
  "use strict";

  const MIN_CHARS = 30;
  const MAX_CHARS = 12000;
  const MAX_FILE_BYTES = 5 * 1024 * 1024;
  const REQUEST_TIMEOUT_MS = 115000;

  const $ = (id) => document.getElementById(id);
  const form = $("analyze-form");
  const cv = $("cv");
  const job = $("job");
  const language = $("language");
  const analyzeButton = $("analyze");
  const cancelButton = $("cancel-button");
  const statusLine = $("form-status");
  const alertBox = $("form-alert");
  const results = $("results");
  const fileInput = $("cv-file");
  const uploadButton = $("upload-button");
  const dropzone = $("cv-dropzone");
  const uploadEmpty = $("upload-empty");
  const uploadFile = $("upload-file");
  const uploadProgress = $("upload-progress");
  const progress = $("progress");
  const progressSteps = [...document.querySelectorAll("#progress-steps li")];
  const progressTime = $("progress-time");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  let controller = null;
  let lastReport = null;

  const SAMPLE_CV = `Alex Lindqvist (fictional example)
IT Operations Technician student, Stockholm

Education
IT Operations Technician (IT-drifttekniker), vocational college, 2025–2027

Experience
Internship, IT support, 2026
- Answered user tickets by phone and in the ticket system
- Reset passwords and managed user accounts in Active Directory
- Installed and configured Windows 11 laptops for new employees

Skills
Windows Server, Active Directory, Group Policy, DNS, DHCP
Linux (Ubuntu) command line, Bash basics
AWS EC2 and security groups (course labs), Terraform basics
Networking: VLANs, OSPF, ACLs in Cisco Packet Tracer
Languages: English (fluent), Swedish (intermediate)`;

  const SAMPLE_JOB = `Junior IT Technician – Service Desk (fictional example)

We are looking for a junior IT technician to join our service desk in Stockholm.

You will:
- Help colleagues with IT issues by phone, chat and on site
- Manage user accounts in Active Directory and Microsoft 365
- Set up and maintain laptops, phones and printers
- Document solutions in our knowledge base

We think you have:
- An IT education or similar experience
- Knowledge of Windows 10/11 and Active Directory
- Experience with Microsoft 365 / Intune (a plus)
- ITIL Foundation certification (a plus)
- Good communication skills in Swedish and English`;

  // ---------- theme ----------
  const themeToggle = $("theme-toggle");
  const systemLight = window.matchMedia("(prefers-color-scheme: light)");
  const currentTheme = () => document.documentElement.dataset.theme || (systemLight.matches ? "light" : "dark");
  function paintThemeToggle() {
    const isLight = currentTheme() === "light";
    themeToggle.setAttribute("aria-pressed", String(isLight));
    themeToggle.querySelector(".theme-toggle-label").textContent = isLight ? "Dark theme" : "Light theme";
    themeToggle.setAttribute("aria-label", isLight ? "Switch to dark theme" : "Switch to light theme");
  }
  themeToggle.addEventListener("click", () => {
    const next = currentTheme() === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("cb-theme", next); } catch (e) { /* not saved; fine */ }
    paintThemeToggle();
  });
  systemLight.addEventListener("change", paintThemeToggle);
  paintThemeToggle();

  // ---------- counters and validation ----------
  const formatCount = (n) => n.toLocaleString("en-US");
  function updateCount(field) {
    const counter = $(`${field.id}-count`);
    const length = field.value.trim().length;
    counter.textContent = `${formatCount(field.value.length)} / ${formatCount(MAX_CHARS)}`;
    counter.classList.toggle("is-over", field.value.length > MAX_CHARS);
    if (field.getAttribute("aria-invalid") === "true" && length >= MIN_CHARS && field.value.length <= MAX_CHARS) {
      setFieldError(field, "");
    }
  }
  function setFieldError(field, message) {
    const error = $(`${field.id}-error`);
    error.textContent = message;
    error.hidden = !message;
    field.setAttribute("aria-invalid", message ? "true" : "false");
  }
  function validate() {
    let firstInvalid = null;
    for (const [field, name] of [[cv, "your CV"], [job, "the job advertisement"]]) {
      const length = field.value.trim().length;
      let message = "";
      if (length === 0) message = `Add ${name} to compare.`;
      else if (length < MIN_CHARS) message = `Add a bit more text: at least ${MIN_CHARS} characters (now ${length}).`;
      else if (field.value.length > MAX_CHARS) message = `Shorten the text to ${formatCount(MAX_CHARS)} characters or fewer.`;
      setFieldError(field, message);
      if (message && !firstInvalid) firstInvalid = field;
    }
    if (firstInvalid) firstInvalid.focus();
    return !firstInvalid;
  }
  [cv, job].forEach((field) => {
    field.addEventListener("input", () => updateCount(field));
    updateCount(field);
  });

  // ---------- messages ----------
  function showAlert(message, kind = "error") {
    alertBox.textContent = "";
    if (kind === "error") {
      const strong = document.createElement("strong");
      strong.textContent = "Not compared. ";
      alertBox.append(strong);
    }
    alertBox.append(document.createTextNode(message));
    alertBox.classList.toggle("is-info", kind !== "error");
    alertBox.hidden = false;
  }
  function clearMessages() {
    alertBox.hidden = true;
    alertBox.textContent = "";
    statusLine.textContent = "";
  }

  async function readJson(response) {
    try { return await response.json(); } catch (e) { return null; }
  }
  function messageForStatus(status) {
    if (status === 413) return "The request is too large. CV files can be at most 5 MB.";
    if (status === 429) return "Too many requests. Please wait a minute and try again.";
    if (status === 502 || status === 503) return "The server could not reach the AI service. Please try again in a moment.";
    if (status === 504) return "The AI service took too long to respond. Please try again.";
    return `The server answered with an unexpected error (HTTP ${status}). Please try again.`;
  }

  // ---------- CV upload ----------
  uploadButton.addEventListener("click", () => fileInput.click());
  $("upload-replace").addEventListener("click", () => fileInput.click());
  $("upload-remove").addEventListener("click", () => {
    showFile(null);
    cv.value = "";
    updateCount(cv);
    statusLine.textContent = "The file and its text were removed.";
    uploadButton.focus();
  });

  function formatSize(bytes) {
    return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }
  function showFile(info) {
    uploadEmpty.hidden = Boolean(info);
    uploadFile.hidden = !info;
    dropzone.classList.toggle("has-file", Boolean(info));
    if (!info) return;
    $("upload-file-name").textContent = info.name;
    const parts = [info.type.toUpperCase(), formatSize(info.size)];
    if (info.pages) parts.push(`${info.pages} ${info.pages === 1 ? "page" : "pages"}`);
    parts.push(`${formatCount(info.characters)} characters`);
    $("upload-file-meta").textContent = parts.join(", ");
  }
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) uploadCv(fileInput.files[0]);
    fileInput.value = "";
  });
  ["dragenter", "dragover"].forEach((type) => dropzone.addEventListener(type, (event) => {
    if (![...event.dataTransfer.types].includes("Files")) return;
    event.preventDefault();
    dropzone.classList.add("is-dragging");
  }));
  ["dragleave", "drop"].forEach((type) => dropzone.addEventListener(type, () => dropzone.classList.remove("is-dragging")));
  dropzone.addEventListener("drop", (event) => {
    if (!event.dataTransfer.files.length) return;
    event.preventDefault();
    uploadCv(event.dataTransfer.files[0]);
  });

  async function uploadCv(file) {
    clearMessages();
    if (!/\.(pdf|docx)$/i.test(file.name)) {
      showAlert("Only PDF and DOCX files are supported. You can also paste the text.");
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      showAlert("The file is larger than 5 MB. Please upload a smaller file or paste the text.");
      return;
    }
    const body = new FormData();
    body.append("file", file);
    uploadButton.disabled = true;
    uploadProgress.hidden = false;
    statusLine.textContent = `Reading ${file.name}…`;
    try {
      const response = await fetch("/api/extract-cv", { method: "POST", body });
      const data = await readJson(response);
      if (!response.ok || !data || typeof data.text !== "string") {
        statusLine.textContent = "";
        showAlert((data && data.error) || messageForStatus(response.status));
        return;
      }
      cv.value = data.text;
      updateCount(cv);
      setFieldError(cv, "");
      showFile({ name: file.name, size: file.size, type: data.file_type, pages: data.pages, characters: data.characters });
      const pages = data.pages ? ` (${data.pages} ${data.pages === 1 ? "page" : "pages"})` : "";
      statusLine.textContent = `Text from ${file.name}${pages} was added. Check it before you compare.`;
      if (data.truncated) {
        showAlert(`The CV was longer than ${formatCount(MAX_CHARS)} characters, so only the first part was added.`, "info");
      }
      cv.focus();
    } catch (e) {
      statusLine.textContent = "";
      showAlert("The file could not be sent. Check your internet connection and try again.");
    } finally {
      uploadButton.disabled = false;
      uploadProgress.hidden = true;
    }
  }

  // ---------- sample and clear ----------
  $("sample-button").addEventListener("click", () => {
    cv.value = SAMPLE_CV;
    job.value = SAMPLE_JOB;
    [cv, job].forEach((f) => { updateCount(f); setFieldError(f, ""); });
    clearMessages();
    statusLine.textContent = "An example CV and job ad were added. Both are fictional.";
  });
  $("clear-button").addEventListener("click", () => {
    cv.value = "";
    job.value = "";
    [cv, job].forEach((f) => { updateCount(f); setFieldError(f, ""); });
    clearMessages();
    showFile(null);
    results.hidden = true;
    lastReport = null;
    cv.focus();
  });

  // ---------- analysis ----------
  let progressTimer = null;
  function setProgress(isRunning) {
    clearInterval(progressTimer);
    progress.hidden = !isRunning;
    if (!isRunning) return;
    const started = Date.now();
    const tick = () => {
      const seconds = Math.floor((Date.now() - started) / 1000);
      progressTime.textContent = `${seconds} s`;
      let active = 0;
      progressSteps.forEach((li, i) => { if (seconds >= Number(li.dataset.after)) active = i; });
      progressSteps.forEach((li, i) => {
        li.classList.toggle("is-done", i < active);
        li.classList.toggle("is-active", i === active);
      });
    };
    tick();
    progressTimer = setInterval(tick, 500);
    results.hidden = true;
    progress.scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth", block: "center" });
  }

  function setLoading(isLoading) {
    setProgress(isLoading);
    analyzeButton.disabled = isLoading;
    analyzeButton.classList.toggle("is-loading", isLoading);
    analyzeButton.querySelector(".button-label").textContent = isLoading ? "Comparing…" : "Compare CV and job";
    cancelButton.hidden = !isLoading;
    form.setAttribute("aria-busy", String(isLoading));
  }

  cancelButton.addEventListener("click", () => { if (controller) controller.abort("cancelled"); });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessages();
    if (!validate()) return;
    if (!navigator.onLine) {
      showAlert("You seem to be offline. Connect to the internet and try again.");
      return;
    }
    controller = new AbortController();
    const timer = setTimeout(() => controller.abort("timeout"), REQUEST_TIMEOUT_MS);
    setLoading(true);
    statusLine.textContent = "Comparing your CV with the job ad. This usually takes 10–40 seconds.";
    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cv: cv.value, job: job.value, language: language.value }),
        signal: controller.signal,
      });
      const data = await readJson(response);
      if (!response.ok || !data || !data.analysis) {
        statusLine.textContent = "";
        showAlert((data && data.error) || messageForStatus(response.status));
        return;
      }
      renderResults(data);
      statusLine.textContent = "Comparison ready.";
    } catch (e) {
      statusLine.textContent = "";
      const reason = controller.signal.reason;
      if (reason === "cancelled") statusLine.textContent = "Comparison cancelled.";
      else if (reason === "timeout") showAlert("The comparison took too long. Please try again.");
      else showAlert("The server could not be reached. Check your internet connection and try again.");
    } finally {
      clearTimeout(timer);
      controller = null;
      setLoading(false);
    }
  });

  function fillList(listId, emptyId, items) {
    const list = $(listId);
    list.replaceChildren(...items.map((text) => {
      const li = document.createElement("li");
      li.textContent = text;
      return li;
    }));
    if (emptyId) $(emptyId).hidden = items.length > 0;
  }

  function renderResults(data) {
    const a = data.analysis;
    const score = Math.max(0, Math.min(100, Number(a.match_score) || 0));
    results.lang = data.language === "sv" ? "sv" : "en";
    countUp($("score-value"), score);
    $("score-label").textContent = a.score_label || "Match";
    $("score-explanation").textContent = a.score_explanation || "";
    $("disclaimer").textContent = data.disclaimer || "";
    $("disclaimer").lang = "en";
    $("summary").textContent = a.summary || "";
    fillList("matching-skills", "matching-empty", a.matching_skills || []);
    fillList("missing-skills", "missing-empty", a.missing_skills || []);
    const suggestions = a.suggestions || [];
    $("suggestions").replaceChildren(...suggestions.map((text, i) => {
      const li = document.createElement("li");
      const label = document.createElement("label");
      const box = document.createElement("input");
      box.type = "checkbox";
      box.id = `suggestion-${i}`;
      const span = document.createElement("span");
      span.textContent = text;
      label.append(box, span);
      li.append(label);
      return li;
    }));
    $("count-found").textContent = String((a.matching_skills || []).length);
    $("count-missing").textContent = String((a.missing_skills || []).length);
    $("count-suggestions").textContent = String(suggestions.length);
    const letter = a.cover_letter || "";
    $("cover-letter").textContent = letter;
    const words = letter.trim() ? letter.trim().split(/\s+/).length : 0;
    $("letter-words").textContent = words ? `About ${words} words.` : "";

    const fill = $("arch-fill");
    fill.style.strokeDasharray = "0 100";
    results.hidden = false;
    results.classList.remove("is-revealed");
    void results.offsetWidth;
    results.classList.add("is-revealed");
    requestAnimationFrame(() => requestAnimationFrame(() => { fill.style.strokeDasharray = `${score} 100`; }));
    lastReport = buildReport(a, data.disclaimer);
    results.scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth" });
    results.focus({ preventScroll: true });
  }

  function countUp(el, target) {
    if (reduceMotion.matches) { el.textContent = String(target); return; }
    const start = performance.now();
    const duration = 900;
    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      el.textContent = String(Math.round(target * (1 - Math.pow(1 - t, 3))));
      if (t < 1) requestAnimationFrame(step);
    };
    el.textContent = "0";
    requestAnimationFrame(step);
  }

  function buildReport(a, disclaimer) {
    const list = (items) => (items.length ? items.map((t) => `- ${t}`).join("\n") : "- (none)");
    return [
      "CareerBridge AI – CV and job comparison",
      `Created: ${new Date().toLocaleString("sv-SE")}`,
      "",
      `Match score (AI estimate): ${a.match_score}% – ${a.score_label}`,
      a.score_explanation,
      disclaimer,
      "",
      "SUMMARY", a.summary, "",
      "FOUND IN YOUR CV", list(a.matching_skills || []), "",
      "ASKED FOR, BUT NOT SHOWN IN YOUR CV", list(a.missing_skills || []), "",
      "HOW TO IMPROVE YOUR CV", list(a.suggestions || []), "",
      "COVER LETTER DRAFT", a.cover_letter, "",
    ].join("\n");
  }

  // ---------- result actions ----------
  const copyButton = $("copy-letter");
  copyButton.addEventListener("click", async () => {
    const text = $("cover-letter").textContent;
    let copied = false;
    try {
      await navigator.clipboard.writeText(text);
      copied = true;
    } catch (e) {
      const range = document.createRange();
      range.selectNodeContents($("cover-letter"));
      const selection = getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      copied = document.execCommand && document.execCommand("copy");
      selection.removeAllRanges();
    }
    copyButton.textContent = copied ? "Copied" : "Copy failed – select the text";
    statusLine.textContent = copied ? "The cover letter was copied." : "";
    setTimeout(() => { copyButton.textContent = "Copy letter"; }, 2500);
  });

  $("download-report").addEventListener("click", () => {
    if (!lastReport) return;
    const url = URL.createObjectURL(new Blob([lastReport], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `careerbridge-report-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });

  $("edit-again").addEventListener("click", () => {
    form.scrollIntoView({ behavior: "smooth" });
    cv.focus({ preventScroll: true });
  });
})();
