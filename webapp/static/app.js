// Studio UI logic: everything is visible at once (no wizard steps), picker tiles write into
// the free-text boxes rather than hiding behind their own hidden parameters.

const SOUND_GENRES = ["pop", "rock", "power-metal", "chill-house", "hip-hop", "acoustic"];
const VOICE_PHRASES = ["male vocals", "female vocals", "instrumental"];
const FEEL_PHRASES = ["slow tempo", "mid tempo", "fast tempo"];

let currentSongName = null;
let takesCount = 2;
let pollTimer = null;

function labelFor(slug) {
  return slug.replace(/-/g, " ");
}

function togglePhraseInTextarea(textarea, phrase) {
  const have = textarea.value.split(",").map((p) => p.trim()).filter(Boolean);
  const idx = have.findIndex((p) => p.toLowerCase() === phrase.toLowerCase());
  if (idx >= 0) {
    have.splice(idx, 1);
  } else {
    have.push(phrase);
  }
  textarea.value = have.join(", ");
}

function buildPillRow(container, phrases, { withPreview = false } = {}) {
  phrases.forEach((slugOrPhrase) => {
    const label = withPreview ? labelFor(slugOrPhrase) : slugOrPhrase;
    const phrase = label;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "st-pill";
    if (withPreview) {
      btn.dataset.testid = `sound-pill-${slugOrPhrase}`;
    }
    btn.innerHTML = withPreview
      ? `${label} <span class="st-play">▶ 0:10</span>`
      : label;
    btn.addEventListener("click", (ev) => {
      btn.classList.toggle("selected");
      togglePhraseInTextarea(document.getElementById("instructions-text"), phrase);
      if (withPreview && ev.target.classList.contains("st-play")) {
        new Audio(`/api/previews/${slugOrPhrase}`).play().catch(() => {});
      }
    });
    container.appendChild(btn);
  });
}

function setupPills() {
  buildPillRow(document.getElementById("sound-pills"), SOUND_GENRES, { withPreview: true });
  buildPillRow(document.getElementById("voice-pills"), VOICE_PHRASES);
  buildPillRow(document.getElementById("feel-pills"), FEEL_PHRASES);
}

function setupEffortBar() {
  const stops = document.querySelectorAll(".st-effort-stop");
  stops.forEach((stop, i) => {
    stop.addEventListener("click", async () => {
      stops.forEach((s, j) => {
        s.classList.toggle("active", j === i);
        s.classList.toggle("filled", j <= i);
      });
      const level = stop.dataset.level;
      if (level === "manual") return;
      const lyricsBox = document.getElementById("lyrics-text");
      try {
        const resp = await fetch("/api/assist/lyrics", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            level,
            idea_text: document.getElementById("instructions-text").value,
            current_lyrics: lyricsBox.value,
          }),
        });
        const data = await resp.json();
        if (resp.ok) {
          lyricsBox.value = data.lyrics;
        } else {
          showJobStatus(`Lyrics assist unavailable: ${data.error}`, "error");
        }
      } catch (err) {
        showJobStatus(`Lyrics assist unavailable: ${err}`, "error");
      }
    });
  });
}

function setupTakesStepper() {
  document.getElementById("takes-count").textContent = takesCount;
  document.getElementById("takes-minus").addEventListener("click", () => {
    takesCount = Math.max(1, takesCount - 1);
    document.getElementById("takes-count").textContent = takesCount;
  });
  document.getElementById("takes-plus").addEventListener("click", () => {
    takesCount += 1;
    document.getElementById("takes-count").textContent = takesCount;
  });
}

function setupMoreOptionsToggle() {
  const toggle = document.getElementById("more-options-toggle");
  const fields = document.getElementById("more-options");
  toggle.addEventListener("click", () => {
    const open = fields.classList.toggle("open");
    toggle.textContent = open ? "▾ More options (length, tempo, key)" : "▸ More options (length, tempo, key)";
  });
}

function showJobStatus(text, cls) {
  const el = document.getElementById("job-status");
  el.hidden = false;
  el.textContent = text;
  el.className = `st-job-status ${cls || ""}`.trim();
}

async function pollJob(jobId) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const resp = await fetch(`/api/jobs/${jobId}`);
    const status = await resp.json();
    if (status.state === "done") {
      clearInterval(pollTimer);
      showJobStatus("Done! New take ready below.", "done");
      await loadSong(currentSongName);
    } else if (status.state === "error") {
      clearInterval(pollTimer);
      showJobStatus(`Failed: ${status.error}`, "error");
    } else {
      showJobStatus(status.state === "queued" ? "Queued (another song is generating)..." : "Generating...");
    }
  }, 1000);
}

async function makeSong() {
  showJobStatus("Starting...");  // first statement: visible the instant the click is handled, no race
  if (!currentSongName) {
    await ensureCurrentSong();
  }
  const body = {
    caption: document.getElementById("instructions-text").value,
    lyrics: document.getElementById("lyrics-text").value,
    takes: takesCount,
    duration: Number(document.getElementById("opt-duration").value) || 120,
    key: document.getElementById("opt-key").value || "",
  };
  const bpmVal = document.getElementById("opt-bpm").value;
  if (bpmVal) body.bpm = Number(bpmVal);
  const resp = await fetch(`/api/songs/${currentSongName}/make`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json();
  pollJob(data.job_id);
}

function renderTakes(takes) {
  const list = document.getElementById("takes-list");
  list.innerHTML = "";
  if (!takes.length) {
    list.innerHTML = '<span class="st-ai-hint" style="opacity:.85">Nothing yet. Make the song below to get started.</span>';
    return;
  }
  takes.forEach((take, i) => {
    const div = document.createElement("div");
    div.className = "st-take";
    div.innerHTML = `<audio controls src="/api/songs/${currentSongName}/takes/${i}"></audio>
                      <span class="st-take-meta">${take.id}</span>`;
    list.appendChild(div);
  });
}

async function loadSong(name) {
  currentSongName = name;
  const resp = await fetch(`/api/songs/${name}`);
  if (!resp.ok) {
    document.getElementById("song-name").textContent = name;
    document.getElementById("song-versions").textContent = "0 takes so far";
    renderTakes([]);
    return;
  }
  const data = await resp.json();
  document.getElementById("song-name").textContent = data.song.title || name;
  document.getElementById("song-versions").textContent = `${data.takes.length} take(s) so far`;
  document.getElementById("instructions-text").value = data.song.generated?.prompt || "";
  document.getElementById("lyrics-text").value = data.song.generated?.lyrics || "";
  renderTakes(data.takes);
}

async function ensureCurrentSong() {
  if (currentSongName) return;
  const resp = await fetch("/api/songs/new-name", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "New Song" }),
  });
  const data = await resp.json();
  currentSongName = data.name;
  document.getElementById("song-name").textContent = "New Song";
}

async function loadSongList() {
  const resp = await fetch("/api/songs");
  const list = await resp.json();
  const container = document.getElementById("song-list");
  const filterText = document.getElementById("song-filter").value.toLowerCase();
  container.innerHTML = "";
  list.filter((s) => s.title.toLowerCase().includes(filterText)).forEach((s) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "st-pill";
    btn.textContent = `${s.title} (${s.take_count})`;
    btn.addEventListener("click", () => loadSong(s.name));
    container.appendChild(btn);
  });
}

function setupOpenFolderButton() {
  document.getElementById("open-folder-btn").addEventListener("click", async () => {
    if (!currentSongName) return;
    await fetch("/api/open-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: currentSongName }),
    });
  });
}

window.addEventListener("DOMContentLoaded", () => {
  setupPills();
  setupEffortBar();
  setupTakesStepper();
  setupMoreOptionsToggle();
  setupOpenFolderButton();
  document.getElementById("make-button").addEventListener("click", makeSong);
  document.getElementById("song-filter").addEventListener("input", loadSongList);
  loadSongList();
});
