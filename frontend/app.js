const rowsEl = document.querySelector("#trackRows");
const template = document.querySelector("#trackRowTemplate");
const summaryEl = document.querySelector("#summary");
const statusFilter = document.querySelector("#statusFilter");
const refreshButton = document.querySelector("#refreshButton");

const editorTrackName = document.querySelector("#editorTrackName");
const editorTrackMeta = document.querySelector("#editorTrackMeta");
const editorBpm = document.querySelector("#editorBpm");
const editorTime = document.querySelector("#editorTime");
const playButton = document.querySelector("#playButton");
const stopButton = document.querySelector("#stopButton");
const metronomeToggle = document.querySelector("#metronomeToggle");
const volumeRange = document.querySelector("#volumeRange");
const zoomRange = document.querySelector("#zoomRange");
const overviewCanvas = document.querySelector("#waveformOverview");
const detailCanvas = document.querySelector("#waveformDetail");
const analyzeBeatsButton = document.querySelector("#analyzeBeatsButton");
const autoFillPadsButton = document.querySelector("#autoFillPadsButton");
const clearAllPadsButton = document.querySelector("#clearAllPadsButton");
const padPresetSelect = document.querySelector("#padPreset");
const padState = document.querySelector("#padState");
const padGrid = document.querySelector("#padGrid");
const padTemplate = document.querySelector("#padTemplate");

const editableFields = [
  "normalized_decade",
  "normalized_primary_genre",
  "normalized_subgenre",
  "dj_use_tags",
  "review_status",
];

refreshButton.addEventListener("click", loadTracks);
statusFilter.addEventListener("change", loadTracks);

loadTracks();
loadCuePresets();

/* ---------------------------------------------------------------------------
 * Track list: each row is a collapsed summary. Clicking it expands an inline
 * metadata editor and loads the track into the cue editor below.
 * ------------------------------------------------------------------------ */

async function loadCuePresets() {
  try {
    const response = await fetch("/api/cue-presets");
    if (!response.ok) return;
    const payload = await response.json();
    const presets = payload.presets || [];
    const defaultPreset = payload.default_preset || "";
    padPresetSelect.innerHTML = '<option value="">phrase</option>';
    for (const name of presets) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      if (name === defaultPreset) opt.selected = true;
      padPresetSelect.appendChild(opt);
    }
  } catch (_) {}
}

async function loadTracks() {
  rowsEl.innerHTML = "";
  summaryEl.textContent = "Loading tracks...";
  const status = statusFilter.value;
  const url = status ? `/api/tracks?status=${encodeURIComponent(status)}` : "/api/tracks";
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error("Track load failed");
    const payload = await response.json();
    renderTracks(payload.tracks || []);
  } catch (error) {
    summaryEl.textContent = "Unable to load tracks";
    renderTableMessage("Unable to load tracks");
  }
}

function renderTracks(tracks) {
  rowsEl.innerHTML = "";
  summaryEl.textContent = `${tracks.length} tracks`;
  if (tracks.length === 0) {
    renderTableMessage("No tracks");
    return;
  }
  for (const track of tracks) {
    renderTrackGroup(track);
  }
}

function renderTrackGroup(track) {
  const fragment = template.content.cloneNode(true);
  const summaryRow = fragment.querySelector(".summaryRow");
  const detailRow = fragment.querySelector(".detailRow");
  summaryRow.dataset.trackId = track.id;
  detailRow.dataset.trackId = track.id;

  setFieldText(summaryRow, "file_name", track.file_name);
  setFieldText(summaryRow, "file_path", track.file_path);
  setFieldText(
    summaryRow,
    "summary_artist_title",
    [track.artist, track.title].filter(Boolean).join(" — ") || "—",
  );
  setFieldText(summaryRow, "summary_confidence", formatConfidence(track.genre_confidence));
  const badge = summaryRow.querySelector('[data-field="summary_status"]');
  if (badge) {
    badge.textContent = track.review_status;
    badge.className = `statusBadge status-${track.review_status}`;
  }

  for (const element of detailRow.querySelectorAll("[data-field]")) {
    const field = element.dataset.field;
    if (field === "missing_fields") {
      element.textContent = (track.missing_fields || []).join("; ");
    } else if (field === "row_state" || field === "history_panel") {
      element.textContent = "";
    } else if (field === "review_required") {
      element.textContent = track.review_required ? "Review required" : "Ready to approve";
      element.className = track.review_required ? "reviewFlag warningFlag" : "reviewFlag";
    } else if (field.endsWith("_confidence")) {
      element.textContent = formatConfidence(track[field]);
      element.className = "";
      const numeric = Number(track[field]);
      if (!Number.isNaN(numeric) && track[field] !== null && track[field] !== "") {
        if (numeric < 0.4) element.classList.add("confidence-low");
        else if (numeric < 0.7) element.classList.add("confidence-mid");
      }
    } else {
      element.textContent = valueOrDash(track[field]);
    }
  }

  for (const field of editableFields) {
    const input = detailRow.querySelector(`[data-input="${field}"]`);
    if (input) input.value = track[field] || "";
  }

  detailRow.querySelector('[data-action="approve"]').addEventListener("click", () => {
    saveTrack(detailRow, summaryRow, "approved");
  });
  detailRow.querySelector('[data-action="save-edit"]').addEventListener("click", () => {
    saveTrack(detailRow, summaryRow, "edited");
  });
  detailRow.querySelector('[data-action="reject"]').addEventListener("click", () => {
    saveTrack(detailRow, summaryRow, "rejected");
  });
  detailRow.querySelector('[data-action="skip"]').addEventListener("click", () => {
    saveTrack(detailRow, summaryRow, "skipped");
  });
  detailRow.querySelector('[data-action="history"]').addEventListener("click", () => {
    loadHistory(detailRow);
  });

  summaryRow.classList.add("selectableRow");
  summaryRow.addEventListener("click", (event) => {
    if (event.target.closest("input, select, button, textarea, .historyPanel")) {
      return;
    }
    const willOpen = detailRow.hidden;
    detailRow.hidden = !willOpen;
    summaryRow.classList.toggle("expanded", willOpen);
    const caret = summaryRow.querySelector(".caret");
    if (caret) caret.textContent = willOpen ? "▾" : "▸";
    if (willOpen) {
      selectTrackForEditor(track, summaryRow);
    }
  });

  rowsEl.appendChild(fragment);
}

function setFieldText(scope, field, value) {
  const el = scope.querySelector(`[data-field="${field}"]`);
  if (el) el.textContent = valueOrDash(value);
}

async function saveTrack(row, summaryRow, forcedStatus = null) {
  const trackId = row.dataset.trackId;
  const actionButtons = row.querySelectorAll("button[data-action]");
  const rowState = row.querySelector('[data-field="row_state"]');
  const payload = {};

  for (const field of editableFields) {
    payload[field] = row.querySelector(`[data-input="${field}"]`).value;
  }
  if (forcedStatus) {
    payload.review_status = forcedStatus;
  }

  for (const button of actionButtons) {
    button.disabled = true;
  }
  rowState.textContent = "Saving...";
  try {
    const response = await fetch(`/api/tracks/${trackId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      rowState.textContent = await responseErrorMessage(response, "Save failed");
      return;
    }

    const result = await response.json();
    const updated = result.track;
    for (const field of editableFields) {
      row.querySelector(`[data-input="${field}"]`).value = updated[field] || "";
    }
    row.querySelector('[data-field="suggested_normalized_label"]').textContent =
      valueOrDash(updated.suggested_normalized_label);
    row.querySelector('[data-field="reason"]').textContent = valueOrDash(updated.reason);
    const reviewFlag = row.querySelector('[data-field="review_required"]');
    reviewFlag.textContent = updated.review_required ? "Review required" : "Ready to approve";
    reviewFlag.className = updated.review_required ? "reviewFlag warningFlag" : "reviewFlag";
    rowState.textContent = "Saved";

    if (summaryRow) {
      const badge = summaryRow.querySelector('[data-field="summary_status"]');
      if (badge) {
        badge.textContent = updated.review_status;
        badge.className = `statusBadge status-${updated.review_status}`;
      }
      setFieldText(summaryRow, "summary_confidence", formatConfidence(updated.genre_confidence));
    }
  } catch (error) {
    rowState.textContent = "Save failed";
  } finally {
    for (const button of actionButtons) {
      button.disabled = false;
    }
  }
}

async function loadHistory(row) {
  const trackId = row.dataset.trackId;
  const panel = row.querySelector('[data-field="history_panel"]');
  panel.textContent = "Loading history...";

  try {
    const response = await fetch(`/api/tracks/${trackId}/history`);
    if (!response.ok) {
      panel.textContent = "History unavailable";
      return;
    }

    const payload = await response.json();
    const history = payload.history || [];
    if (history.length === 0) {
      panel.textContent = "No edits";
      return;
    }

    panel.innerHTML = "";
    for (const record of history.slice(0, 5)) {
      const item = document.createElement("div");
      item.className = "historyItem";
      item.textContent = `${record.timestamp} ${record.source} ${record.action}: ${record.previous_review_status} -> ${record.new_review_status}; ${valueOrDash(record.previous_normalized_primary_genre)} -> ${valueOrDash(record.new_normalized_primary_genre)}; confidence ${formatConfidence(record.confidence_at_action)}; ${valueOrDash(record.reason)}`;
      panel.appendChild(item);
    }
  } catch (error) {
    panel.textContent = "History unavailable";
  }
}

function valueOrDash(value) {
  return value === null || value === undefined || value === "" ? "-" : String(value);
}

function formatConfidence(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return String(value);
  }
  return numeric.toFixed(2);
}

function renderTableMessage(message) {
  rowsEl.innerHTML = "";
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = 5;
  cell.textContent = message;
  row.appendChild(cell);
  rowsEl.appendChild(row);
}

async function responseErrorMessage(response, fallback) {
  try {
    const error = await response.json();
    return error.error || fallback;
  } catch (error) {
    return fallback;
  }
}

/* ---------------------------------------------------------------------------
 * Cue editor: dual-canvas waveform, transport, metronome, volume, zoom,
 * and 8 cue pads. Audio files are never modified.
 * ------------------------------------------------------------------------ */

let audioCtx = null;
let gainNode = null;
let audioBuffer = null;
let sourceNode = null;
let isPlaying = false;
let playStartCtxTime = 0;
let playStartOffset = 0;
let duration = 0;
let selectedTrack = null;
let selectedRowEl = null;
let padsData = [];
let metronomeTimer = null;
let nextBeatTime = 0;
let rafId = null;

let freqBands = null;
let overviewOffscreen = null;
let beatTimestamps = [];
let beatConfidence = 0;
let zoomBeats = 16;
let detailCenter = 0;

playButton.addEventListener("click", togglePlay);
stopButton.addEventListener("click", stopPlayback);
analyzeBeatsButton.addEventListener("click", analyzeTrackBeats);
autoFillPadsButton.addEventListener("click", autoFillPads);
clearAllPadsButton.addEventListener("click", clearAllPads);
volumeRange.addEventListener("input", () => {
  if (gainNode) gainNode.gain.value = volumeRange.value / 100;
});
zoomRange.addEventListener("input", () => {
  zoomBeats = Number(zoomRange.value);
  drawAll();
});
metronomeToggle.addEventListener("change", () => {
  if (metronomeToggle.checked && isPlaying) {
    startMetronome();
  } else {
    stopMetronome();
  }
});
overviewCanvas.addEventListener("click", (event) => {
  if (!audioBuffer || duration <= 0) return;
  const rect = overviewCanvas.getBoundingClientRect();
  const t = ((event.clientX - rect.left) / rect.width) * duration;
  seek(t);
});
detailCanvas.addEventListener("click", (event) => {
  if (!audioBuffer || duration <= 0) return;
  const rect = detailCanvas.getBoundingClientRect();
  const frac = (event.clientX - rect.left) / rect.width;
  const windowSec = detailWindowSeconds();
  const start = detailCenter - windowSec / 2;
  seek(start + frac * windowSec);
});
detailCanvas.addEventListener("wheel", (event) => {
  event.preventDefault();
  const delta = event.deltaY > 0 ? 4 : -4;
  zoomBeats = Math.max(4, Math.min(64, zoomBeats + delta));
  zoomRange.value = zoomBeats;
  drawAll();
}, { passive: false });
window.addEventListener("resize", () => {
  overviewOffscreen = null;
  if (selectedTrack) drawAll();
});

function getAudioContext() {
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    gainNode = audioCtx.createGain();
    gainNode.gain.value = volumeRange.value / 100;
    gainNode.connect(audioCtx.destination);
  }
  return audioCtx;
}

async function selectTrackForEditor(track, rowEl) {
  if (selectedRowEl) selectedRowEl.classList.remove("selectedRow");
  selectedRowEl = rowEl;
  if (rowEl) rowEl.classList.add("selectedRow");

  stopPlayback();
  audioBuffer = null;
  duration = 0;
  playStartOffset = 0;
  selectedTrack = track;
  freqBands = null;
  overviewOffscreen = null;
  beatTimestamps = [];
  beatConfidence = 0;
  detailCenter = 0;

  editorTrackName.textContent = track.file_name || track.file_path || "Track";
  editorTrackMeta.textContent = [track.artist, track.title].filter(Boolean).join(" — ");
  editorBpm.textContent = track.bpm ? `BPM ${Number(track.bpm).toFixed(1)}` : "BPM —";
  analyzeBeatsButton.disabled = false;
  autoFillPadsButton.disabled = false;
  clearAllPadsButton.disabled = false;
  padPresetSelect.disabled = false;

  await loadPads(track.id);
  await Promise.all([loadAudio(track), loadBeats(track.id)]);
}

async function loadBeats(trackId) {
  try {
    const response = await fetch(`/api/tracks/${trackId}/beats`);
    if (!response.ok) return;
    const payload = await response.json();
    beatTimestamps = payload.beats || [];
    beatConfidence = payload.beat_confidence || 0;
  } catch (_) {
    beatTimestamps = [];
    beatConfidence = 0;
  }
}

async function loadAudio(track) {
  playButton.disabled = true;
  stopButton.disabled = true;
  editorTime.textContent = "Loading audio…";
  drawCanvasMessage(overviewCanvas, 80, "Loading audio…");
  drawCanvasMessage(detailCanvas, 120, "");
  try {
    const response = await fetch(`/api/audio?path=${encodeURIComponent(track.file_path)}`);
    if (!response.ok) throw new Error("audio load failed");
    const arrayBuffer = await response.arrayBuffer();
    audioBuffer = await getAudioContext().decodeAudioData(arrayBuffer);
    duration = audioBuffer.duration;
    playButton.disabled = false;
    stopButton.disabled = false;

    drawCanvasMessage(overviewCanvas, 80, "Analyzing frequencies…");
    drawCanvasMessage(detailCanvas, 120, "Analyzing frequencies…");
    freqBands = await computeFrequencyBands(audioBuffer);
    overviewOffscreen = null;

    drawAll();
    updateTime();
    renderPads();
  } catch (error) {
    audioBuffer = null;
    editorTime.textContent = "Audio unavailable";
    drawCanvasMessage(overviewCanvas, 80, "Audio unavailable");
    drawCanvasMessage(detailCanvas, 120, "");
  }
}

function drawCanvasMessage(canvas, cssHeight, msg) {
  const cssWidth = canvas.clientWidth || 800;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = cssWidth * dpr;
  canvas.height = cssHeight * dpr;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--waveform-bg").trim() || "#1a1a2e";
  ctx.fillRect(0, 0, cssWidth, cssHeight);
  if (msg) {
    ctx.fillStyle = "rgba(255,255,255,0.6)";
    ctx.font = "13px sans-serif";
    ctx.fillText(msg, 10, cssHeight / 2 + 4);
  }
}

function togglePlay() {
  if (!audioBuffer) return;
  if (isPlaying) {
    pause();
  } else {
    startPlaybackFrom(playStartOffset >= duration ? 0 : playStartOffset);
  }
}

function startPlaybackFrom(offset) {
  if (!audioBuffer) return;
  const ctx = getAudioContext();
  if (ctx.state === "suspended") ctx.resume();
  stopSource();
  sourceNode = ctx.createBufferSource();
  sourceNode.buffer = audioBuffer;
  sourceNode.connect(gainNode);
  sourceNode.onended = handleSourceEnded;
  playStartOffset = Math.max(0, Math.min(offset, duration));
  playStartCtxTime = ctx.currentTime;
  sourceNode.start(0, playStartOffset);
  isPlaying = true;
  playButton.textContent = "⏸ Pause";
  startRAF();
  resetMetronome();
  if (metronomeToggle.checked) startMetronome();
}

function pause() {
  if (!isPlaying) return;
  const pos = currentPosition();
  stopSource();
  isPlaying = false;
  playStartOffset = Math.min(pos, duration);
  playButton.textContent = "▶ Play";
  stopMetronome();
  stopRAF();
  detailCenter = playStartOffset;
  drawAll();
  updateTime();
}

function stopPlayback() {
  stopSource();
  isPlaying = false;
  playStartOffset = 0;
  playButton.textContent = "▶ Play";
  stopMetronome();
  stopRAF();
  detailCenter = 0;
  drawAll();
  updateTime();
}

function stopSource() {
  if (sourceNode) {
    sourceNode.onended = null;
    try { sourceNode.stop(); } catch (_) {}
    sourceNode.disconnect();
    sourceNode = null;
  }
}

function handleSourceEnded() {
  isPlaying = false;
  sourceNode = null;
  playStartOffset = 0;
  playButton.textContent = "▶ Play";
  stopMetronome();
  stopRAF();
  detailCenter = 0;
  drawAll();
  updateTime();
}

function seek(position) {
  const clamped = Math.max(0, Math.min(position, duration));
  detailCenter = clamped;
  if (isPlaying) {
    startPlaybackFrom(clamped);
  } else {
    playStartOffset = clamped;
    drawAll();
    updateTime();
  }
}

function currentPosition() {
  if (!isPlaying) return playStartOffset;
  return Math.min(playStartOffset + (getAudioContext().currentTime - playStartCtxTime), duration);
}

function startRAF() {
  if (!rafId) rafId = requestAnimationFrame(tick);
}

function stopRAF() {
  if (rafId) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }
}

function tick() {
  const pos = currentPosition();
  detailCenter = pos;
  drawAll();
  updateTime();
  rafId = requestAnimationFrame(tick);
}

function updateTime() {
  editorTime.textContent = `${formatTime(currentPosition())} / ${formatTime(duration)}`;
}

/* ---- Metronome ---- */

function metronomeAnchor() {
  const first = padsData.find((pad) => pad.timestamp_seconds != null);
  return first ? first.timestamp_seconds : 0;
}

function resetMetronome() {
  if (!selectedTrack || !selectedTrack.bpm) return;
  const secPerBeat = 60 / Number(selectedTrack.bpm);
  const pos = currentPosition();
  const anchor = metronomeAnchor();
  const beatsFromAnchor = Math.ceil((pos - anchor) / secPerBeat);
  nextBeatTime = anchor + beatsFromAnchor * secPerBeat;
}

function startMetronome() {
  if (metronomeTimer || !selectedTrack || !selectedTrack.bpm) return;
  resetMetronome();
  metronomeTimer = setInterval(scheduleMetronome, 25);
}

function stopMetronome() {
  if (metronomeTimer) {
    clearInterval(metronomeTimer);
    metronomeTimer = null;
  }
}

function scheduleMetronome() {
  if (!isPlaying || !selectedTrack || !selectedTrack.bpm) return;
  const ctx = getAudioContext();
  const secPerBeat = 60 / Number(selectedTrack.bpm);
  const lookahead = 0.15;
  const pos = currentPosition();
  while (nextBeatTime < pos + lookahead) {
    if (nextBeatTime >= pos - 0.02 && nextBeatTime <= duration) {
      clickAt(ctx, ctx.currentTime + Math.max(0, nextBeatTime - pos));
    }
    nextBeatTime += secPerBeat;
  }
}

function clickAt(ctx, when) {
  const osc = ctx.createOscillator();
  const clickGain = ctx.createGain();
  osc.type = "square";
  osc.frequency.value = 1000;
  clickGain.gain.setValueAtTime(0.0001, when);
  clickGain.gain.exponentialRampToValueAtTime(1.0, when + 0.001);
  clickGain.gain.exponentialRampToValueAtTime(0.0001, when + 0.04);
  osc.connect(clickGain).connect(ctx.destination);
  osc.start(when);
  osc.stop(when + 0.05);
}

/* ---- Frequency Analysis (three-band FFT via OfflineAudioContext) ---- */

async function computeFrequencyBands(buffer) {
  const sampleRate = buffer.sampleRate;
  const length = buffer.length;
  const numChannels = buffer.numberOfChannels;

  async function renderFiltered(type, freq) {
    const offline = new OfflineAudioContext(1, length, sampleRate);
    const source = offline.createBufferSource();
    source.buffer = buffer;
    const filter = offline.createBiquadFilter();
    filter.type = type;
    filter.frequency.value = freq;
    if (type === "bandpass") {
      filter.Q.value = 1.2;
    }
    source.connect(filter);
    filter.connect(offline.destination);
    source.start(0);
    const rendered = await offline.startRendering();
    return rendered.getChannelData(0);
  }

  const [lowData, midData, highData] = await Promise.all([
    renderFiltered("lowpass", 250),
    renderFiltered("bandpass", 1000),
    renderFiltered("highpass", 4000),
  ]);

  const bucketSize = 2048;
  const numBuckets = Math.ceil(length / bucketSize);
  const low = new Float32Array(numBuckets);
  const mid = new Float32Array(numBuckets);
  const high = new Float32Array(numBuckets);

  for (let i = 0; i < numBuckets; i++) {
    const start = i * bucketSize;
    const end = Math.min(start + bucketSize, length);
    let sumL = 0, sumM = 0, sumH = 0;
    for (let j = start; j < end; j++) {
      sumL += lowData[j] * lowData[j];
      sumM += midData[j] * midData[j];
      sumH += highData[j] * highData[j];
    }
    const n = end - start;
    low[i] = Math.sqrt(sumL / n);
    mid[i] = Math.sqrt(sumM / n);
    high[i] = Math.sqrt(sumH / n);
  }

  let maxVal = 0;
  for (let i = 0; i < numBuckets; i++) {
    const total = low[i] + mid[i] + high[i];
    if (total > maxVal) maxVal = total;
  }
  if (maxVal > 0) {
    for (let i = 0; i < numBuckets; i++) {
      low[i] /= maxVal;
      mid[i] /= maxVal;
      high[i] /= maxVal;
    }
  }

  return { low, mid, high, numBuckets, bucketSize, sampleRate: sampleRate };
}

/* ---- Waveform Drawing ---- */

function drawAll() {
  drawOverview();
  drawDetail();
}

function getStyle(prop) {
  return getComputedStyle(document.documentElement).getPropertyValue(prop).trim();
}

function drawOverview() {
  const canvas = overviewCanvas;
  const cssWidth = canvas.clientWidth || 800;
  const cssHeight = 80;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = cssWidth * dpr;
  canvas.height = cssHeight * dpr;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const bg = getStyle("--waveform-bg") || "#1a1a2e";
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, cssWidth, cssHeight);

  if (!freqBands || !audioBuffer) {
    ctx.fillStyle = "rgba(255,255,255,0.5)";
    ctx.font = "13px sans-serif";
    ctx.fillText("No waveform loaded", 10, cssHeight / 2 + 4);
    return;
  }

  if (!overviewOffscreen || overviewOffscreen.width !== cssWidth * dpr) {
    overviewOffscreen = document.createElement("canvas");
    overviewOffscreen.width = cssWidth * dpr;
    overviewOffscreen.height = cssHeight * dpr;
    const offCtx = overviewOffscreen.getContext("2d");
    offCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    offCtx.fillStyle = bg;
    offCtx.fillRect(0, 0, cssWidth, cssHeight);
    renderFreqWaveform(offCtx, cssWidth, cssHeight, freqBands, 0, duration);
    renderBeatGrid(offCtx, cssWidth, cssHeight, 0, duration, false);
  }

  ctx.drawImage(overviewOffscreen, 0, 0);

  if (duration > 0) {
    const windowSec = detailWindowSeconds();
    const startFrac = Math.max(0, (detailCenter - windowSec / 2) / duration);
    const endFrac = Math.min(1, (detailCenter + windowSec / 2) / duration);
    ctx.fillStyle = getStyle("--waveform-zoom-region") || "rgba(255,255,255,0.08)";
    ctx.fillRect(startFrac * cssWidth, 0, (endFrac - startFrac) * cssWidth, cssHeight);

    for (const pad of padsData) {
      if (pad.timestamp_seconds == null) continue;
      const x = (pad.timestamp_seconds / duration) * cssWidth;
      ctx.fillStyle = getStyle("--waveform-cue") || "#e74c3c";
      ctx.fillRect(x, 0, 1.5, cssHeight);
      ctx.font = "9px monospace";
      ctx.fillText(String(pad.pad_index + 1), x + 2, 10);
    }

    const playheadX = (currentPosition() / duration) * cssWidth;
    ctx.fillStyle = getStyle("--waveform-playhead") || "#ffffff";
    ctx.fillRect(playheadX, 0, 2, cssHeight);
  }
}

function drawDetail() {
  const canvas = detailCanvas;
  const cssWidth = canvas.clientWidth || 800;
  const cssHeight = 120;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = cssWidth * dpr;
  canvas.height = cssHeight * dpr;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const bg = getStyle("--waveform-bg") || "#1a1a2e";
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, cssWidth, cssHeight);

  if (!freqBands || !audioBuffer) return;

  const windowSec = detailWindowSeconds();
  const startTime = Math.max(0, detailCenter - windowSec / 2);
  const endTime = Math.min(duration, startTime + windowSec);

  renderFreqWaveform(ctx, cssWidth, cssHeight, freqBands, startTime, endTime);
  renderBeatGrid(ctx, cssWidth, cssHeight, startTime, endTime, true);

  if (duration > 0) {
    for (const pad of padsData) {
      if (pad.timestamp_seconds == null) continue;
      if (pad.timestamp_seconds < startTime || pad.timestamp_seconds > endTime) continue;
      const x = ((pad.timestamp_seconds - startTime) / (endTime - startTime)) * cssWidth;
      ctx.fillStyle = getStyle("--waveform-cue") || "#e74c3c";
      ctx.fillRect(x, 0, 2, cssHeight);
      ctx.save();
      ctx.font = "10px monospace";
      ctx.fillStyle = getStyle("--waveform-cue") || "#e74c3c";
      ctx.translate(x + 12, cssHeight - 6);
      ctx.rotate(-Math.PI / 2);
      ctx.fillText(pad.label || `Pad ${pad.pad_index + 1}`, 0, 0);
      ctx.restore();
    }

    const pos = currentPosition();
    if (pos >= startTime && pos <= endTime) {
      const playheadX = ((pos - startTime) / (endTime - startTime)) * cssWidth;
      ctx.fillStyle = getStyle("--waveform-playhead") || "#ffffff";
      ctx.fillRect(playheadX, 0, 2, cssHeight);
    }
  }
}

function detailWindowSeconds() {
  if (beatTimestamps.length >= 2) {
    const avgBeatDur = beatTimestamps[beatTimestamps.length - 1] / (beatTimestamps.length - 1);
    return zoomBeats * avgBeatDur;
  }
  if (selectedTrack && selectedTrack.bpm && Number(selectedTrack.bpm) > 0) {
    return zoomBeats * (60 / Number(selectedTrack.bpm));
  }
  return zoomBeats * 0.5;
}

function renderFreqWaveform(ctx, width, height, bands, startTime, endTime) {
  const { low, mid, high, numBuckets, bucketSize, sampleRate } = bands;
  const midY = height / 2;
  const colorLow = getStyle("--waveform-low") || "#e74c3c";
  const colorMid = getStyle("--waveform-mid") || "#2ecc71";
  const colorHigh = getStyle("--waveform-high") || "#3498db";

  const startBucket = Math.floor((startTime * sampleRate) / bucketSize);
  const endBucket = Math.ceil((endTime * sampleRate) / bucketSize);

  for (let x = 0; x < width; x++) {
    const frac = x / width;
    const bi = startBucket + frac * (endBucket - startBucket);
    const idx = Math.min(Math.floor(bi), numBuckets - 1);
    if (idx < 0) continue;

    const l = low[idx] || 0;
    const m = mid[idx] || 0;
    const h = high[idx] || 0;
    const total = (l + m + h) * midY * 0.95;

    const hH = h / (l + m + h + 0.0001) * total;
    const mH = m / (l + m + h + 0.0001) * total;
    const lH = l / (l + m + h + 0.0001) * total;

    ctx.fillStyle = colorLow;
    ctx.fillRect(x, midY - lH / 2, 1, lH || 0.5);
    ctx.fillRect(x, midY, 1, lH / 2 || 0.25);

    ctx.fillStyle = colorMid;
    ctx.fillRect(x, midY - lH / 2 - mH / 2, 1, mH / 2 || 0.25);
    ctx.fillRect(x, midY + lH / 2, 1, mH / 2 || 0.25);

    ctx.fillStyle = colorHigh;
    ctx.fillRect(x, midY - lH / 2 - mH / 2 - hH / 2, 1, hH / 2 || 0.25);
    ctx.fillRect(x, midY + lH / 2 + mH / 2, 1, hH / 2 || 0.25);
  }
}

function renderBeatGrid(ctx, width, height, startTime, endTime, showLabels) {
  if (beatTimestamps.length === 0) return;
  const beatColor = getStyle("--waveform-beat") || "rgba(255,255,255,0.25)";
  const barColor = getStyle("--waveform-bar") || "rgba(255,255,255,0.5)";
  const timeRange = endTime - startTime;
  if (timeRange <= 0) return;

  for (let i = 0; i < beatTimestamps.length; i++) {
    const t = beatTimestamps[i];
    if (t < startTime || t > endTime) continue;
    const x = ((t - startTime) / timeRange) * width;
    const isBar = (i % 4) === 0;
    ctx.fillStyle = isBar ? barColor : beatColor;
    ctx.fillRect(x, 0, isBar ? 1.5 : 0.5, height);

    if (showLabels) {
      const beatInBar = (i % 4) + 1;
      const barNum = Math.floor(i / 4) + 1;
      if (isBar) {
        ctx.fillStyle = "rgba(255,255,255,0.7)";
        ctx.font = "11px monospace";
        ctx.fillText(`Bar ${barNum}`, x + 3, 12);
      } else if (zoomBeats <= 16) {
        ctx.fillStyle = "rgba(255,255,255,0.5)";
        ctx.font = "9px monospace";
        ctx.fillText(String(beatInBar), x + 2, 12);
      }
    }
  }
}

/* ---- Pads ---- */

async function loadPads(trackId) {
  padState.textContent = "Loading pads…";
  try {
    const response = await fetch(`/api/tracks/${trackId}/pads`);
    if (!response.ok) throw new Error("pad load failed");
    const payload = await response.json();
    padsData = payload.pads || [];
  } catch (error) {
    padsData = [];
  }
  renderPads();
  drawAll();
  padState.textContent = padsData.some((pad) => pad.timestamp_seconds != null)
    ? ""
    : "No pad positions yet — Analyze beats, Auto-fill, or Set from the playhead";
}

function renderPads() {
  padGrid.innerHTML = "";
  for (const pad of padsData) {
    const el = padTemplate.content.firstElementChild.cloneNode(true);
    el.dataset.index = pad.pad_index;
    el.querySelector(".padLabel").textContent = pad.label || `Pad ${pad.pad_index + 1}`;
    el.querySelector('[data-field="time"]').textContent =
      pad.timestamp_seconds != null ? formatTime(pad.timestamp_seconds) : "—";

    const jumpBtn = el.querySelector(".padJump");
    jumpBtn.disabled = pad.timestamp_seconds == null || !audioBuffer;
    jumpBtn.addEventListener("click", () => {
      if (pad.timestamp_seconds != null) {
        detailCenter = pad.timestamp_seconds;
        startPlaybackFrom(pad.timestamp_seconds);
      }
    });

    el.querySelector(".padSet").addEventListener("click", () => setPadFromPlayhead(pad.pad_index));
    el.querySelector(".padRename").addEventListener("click", () => renamePad(el, pad));

    const clearBtn = el.querySelector(".padClear");
    if (clearBtn) {
      clearBtn.disabled = pad.timestamp_seconds == null;
      clearBtn.addEventListener("click", () => clearPad(pad.pad_index));
    }

    if (pad.source === "manual") el.classList.add("padManual");
    if (pad.timestamp_seconds == null) el.classList.add("padEmpty");
    padGrid.appendChild(el);
  }
}

async function setPadFromPlayhead(index) {
  if (!selectedTrack) return;
  await savePad(index, { timestamp_seconds: Number(currentPosition().toFixed(3)) });
}

function renamePad(el, pad) {
  const labelSpan = el.querySelector(".padLabel");
  const renameBtn = el.querySelector(".padRename");
  const input = document.createElement("input");
  input.className = "padLabelInput";
  input.value = labelSpan.textContent;

  labelSpan.hidden = true;
  renameBtn.hidden = true;
  el.querySelector(".padTop").appendChild(input);
  input.focus();
  input.select();

  let done = false;
  function finish() {
    if (done) return;
    done = true;
    input.remove();
    labelSpan.hidden = false;
    renameBtn.hidden = false;
  }

  input.addEventListener("keydown", async (event) => {
    if (event.key === "Enter") {
      const value = input.value.trim();
      finish();
      if (value) await savePad(pad.pad_index, { label: value });
    } else if (event.key === "Escape") {
      finish();
    }
  });
  input.addEventListener("blur", finish);
}

async function savePad(index, body) {
  if (!selectedTrack) return;
  try {
    const response = await fetch(`/api/tracks/${selectedTrack.id}/pads/${index}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      padState.textContent = await responseErrorMessage(response, "Pad save failed");
      return;
    }
    await loadPads(selectedTrack.id);
  } catch (error) {
    padState.textContent = "Pad save failed";
  }
}

async function clearPad(index) {
  if (!selectedTrack) return;
  try {
    const response = await fetch(`/api/tracks/${selectedTrack.id}/pads/${index}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      padState.textContent = await responseErrorMessage(response, "Clear failed");
      return;
    }
    await loadPads(selectedTrack.id);
  } catch (error) {
    padState.textContent = "Clear failed";
  }
}

async function clearAllPads() {
  if (!selectedTrack) return;
  try {
    const response = await fetch(`/api/tracks/${selectedTrack.id}/pads`, {
      method: "DELETE",
    });
    if (!response.ok) {
      padState.textContent = await responseErrorMessage(response, "Clear failed");
      return;
    }
    const payload = await response.json();
    padsData = payload.pads || [];
    renderPads();
    drawAll();
    padState.textContent = "All pads cleared";
  } catch (error) {
    padState.textContent = "Clear failed";
  }
}

async function analyzeTrackBeats() {
  if (!selectedTrack) return;
  analyzeBeatsButton.disabled = true;
  padState.textContent = "Analyzing beats…";
  try {
    const response = await fetch(`/api/tracks/${selectedTrack.id}/analyze-beats`, {
      method: "POST",
    });
    if (!response.ok) {
      padState.textContent = await responseErrorMessage(response, "Beat analysis failed");
      return;
    }
    const payload = await response.json();
    padsData = payload.pads || [];
    renderPads();
    await loadBeats(selectedTrack.id);
    overviewOffscreen = null;
    drawAll();
    padState.textContent = `${payload.stored_beats || 0} beats detected — pads filled`;
  } catch (error) {
    padState.textContent = "Beat analysis failed";
  } finally {
    analyzeBeatsButton.disabled = false;
  }
}

async function autoFillPads() {
  if (!selectedTrack) return;
  autoFillPadsButton.disabled = true;
  padState.textContent = "Auto-filling…";
  try {
    const preset = padPresetSelect.value;
    const body = {};
    if (preset) body.preset = preset;
    if (duration > 0) body.total_duration_seconds = duration;
    const response = await fetch(`/api/tracks/${selectedTrack.id}/pads/auto-fill`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      padState.textContent = await responseErrorMessage(response, "Auto-fill failed");
      return;
    }
    const payload = await response.json();
    padsData = payload.pads || [];
    renderPads();
    drawAll();
    const label = preset || "phrase";
    padState.textContent = `Pads filled (${label})`;
  } catch (error) {
    padState.textContent = "Auto-fill failed";
  } finally {
    autoFillPadsButton.disabled = false;
  }
}

function formatTime(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.floor(seconds % 60);
  return `${minutes}:${String(remaining).padStart(2, "0")}`;
}
