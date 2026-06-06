const rowsEl = document.querySelector("#trackRows");
const template = document.querySelector("#trackRowTemplate");
const summaryEl = document.querySelector("#summary");
const statusFilter = document.querySelector("#statusFilter");
const refreshButton = document.querySelector("#refreshButton");
const cueRowsEl = document.querySelector("#cueRows");
const cueStateEl = document.querySelector("#cueState");
const cueFolderPathInput = document.querySelector("#cueFolderPath");
const cuePresetSelect = document.querySelector("#cuePreset");
const cueTemplateRowsInput = document.querySelector("#cueTemplateRows");
const analyzeCueButton = document.querySelector("#analyzeCueButton");
const refreshCueButton = document.querySelector("#refreshCueButton");
const browseFolderButton = document.querySelector("#browseFolderButton");

const editorTrackName = document.querySelector("#editorTrackName");
const editorTrackMeta = document.querySelector("#editorTrackMeta");
const editorBpm = document.querySelector("#editorBpm");
const editorTime = document.querySelector("#editorTime");
const playButton = document.querySelector("#playButton");
const stopButton = document.querySelector("#stopButton");
const metronomeToggle = document.querySelector("#metronomeToggle");
const waveformCanvas = document.querySelector("#waveform");
const autoFillPadsButton = document.querySelector("#autoFillPadsButton");
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
analyzeCueButton.addEventListener("click", analyzeCues);
refreshCueButton.addEventListener("click", loadCuePoints);
browseFolderButton.addEventListener("click", browseForFolder);

loadTracks();
loadCuePoints();

async function loadTracks() {
  rowsEl.innerHTML = "";
  summaryEl.textContent = "Loading tracks...";
  const status = statusFilter.value;
  const url = status ? `/api/tracks?status=${encodeURIComponent(status)}` : "/api/tracks";
  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error("Track load failed");
    }
    const payload = await response.json();
    renderTracks(payload.tracks || []);
  } catch (error) {
    summaryEl.textContent = "Unable to load tracks";
    renderTableMessage("Unable to load tracks");
  }
}

function renderTracks(tracks) {
  summaryEl.textContent = `${tracks.length} tracks`;
  if (tracks.length === 0) {
    renderTableMessage("No tracks");
    return;
  }

  for (const track of tracks) {
    rowsEl.appendChild(renderTrackRow(track));
  }
}

function renderTrackRow(track) {
  const row = template.content.firstElementChild.cloneNode(true);
  row.dataset.trackId = track.id;

  for (const element of row.querySelectorAll("[data-field]")) {
    const field = element.dataset.field;
    if (field === "missing_fields") {
      element.textContent = (track.missing_fields || []).join("; ");
    } else if (field === "row_state") {
      element.textContent = "";
    } else if (field === "review_required") {
      element.textContent = track.review_required ? "Review required" : "Ready to approve";
      element.className = track.review_required ? "reviewFlag warningFlag" : "reviewFlag";
    } else if (field.endsWith("_confidence")) {
      element.textContent = formatConfidence(track[field]);
    } else {
      element.textContent = valueOrDash(track[field]);
    }
  }

  for (const field of editableFields) {
    const input = row.querySelector(`[data-input="${field}"]`);
    input.value = track[field] || "";
  }

  row.querySelector('[data-action="approve"]').addEventListener("click", () => {
    saveTrack(row, "approved");
  });
  row.querySelector('[data-action="save-edit"]').addEventListener("click", () => {
    saveTrack(row, "edited");
  });
  row.querySelector('[data-action="reject"]').addEventListener("click", () => {
    saveTrack(row, "rejected");
  });
  row.querySelector('[data-action="skip"]').addEventListener("click", () => {
    saveTrack(row, "skipped");
  });
  row.querySelector('[data-action="history"]').addEventListener("click", () => {
    loadHistory(row);
  });

  const trackCell = row.querySelector(".trackCell");
  trackCell.classList.add("selectable");
  trackCell.addEventListener("click", () => selectTrackForEditor(track, row));
  return row;
}

async function browseForFolder() {
  browseFolderButton.disabled = true;
  browseFolderButton.textContent = "Opening…";
  try {
    const response = await fetch("/api/browse-folder");
    if (!response.ok) throw new Error();
    const payload = await response.json();
    if (payload.folder) {
      cueFolderPathInput.value = payload.folder;
    }
  } catch {
    // dialog cancelled or unavailable — leave input unchanged
  } finally {
    browseFolderButton.disabled = false;
    browseFolderButton.textContent = "Browse…";
  }
}

async function analyzeCues() {
  const folder = cueFolderPathInput.value.trim();
  const cues = cueTemplateRowsInput.value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  analyzeCueButton.disabled = true;
  cueStateEl.textContent = "Analyzing...";

  try {
    const response = await fetch("/api/analyze-beats", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        folder,
        cue_preset: cuePresetSelect.value,
        cues,
      }),
    });

    if (!response.ok) {
      cueStateEl.textContent = await responseErrorMessage(response, "Analyze failed");
      return;
    }

    const payload = await response.json();
    const summary = payload.summary || {};
    renderCuePoints(payload.cue_points || []);
    cueStateEl.textContent = `${summary.inserted_cue_points || 0} cues inserted`;
    loadTracks();
  } catch (error) {
    cueStateEl.textContent = "Analyze failed";
  } finally {
    analyzeCueButton.disabled = false;
  }
}

async function loadCuePoints() {
  cueStateEl.textContent = "Loading cues...";
  try {
    const response = await fetch("/api/cue-points");
    if (!response.ok) {
      throw new Error("Cue load failed");
    }
    const payload = await response.json();
    renderCuePoints(payload.cue_points || []);
    cueStateEl.textContent = `${(payload.cue_points || []).length} cues`;
  } catch (error) {
    cueStateEl.textContent = "Unable to load cues";
    renderCueTableMessage("Unable to load cues");
  }
}

function renderCuePoints(cuePoints) {
  cueRowsEl.innerHTML = "";
  if (cuePoints.length === 0) {
    renderCueTableMessage("No cues");
    return;
  }

  for (const cuePoint of cuePoints) {
    const row = document.createElement("tr");
    row.dataset.cueId = cuePoint.id;
    row.appendChild(cueCell(cuePoint.file_name || cuePoint.file_path));
    row.appendChild(cueLabelCell(cuePoint));
    row.appendChild(cueCell(cuePoint.beat_index));
    row.appendChild(cueCell(formatSeconds(cuePoint.timestamp_seconds)));
    row.appendChild(cueCell(formatConfidence(cuePoint.cue_confidence)));
    row.appendChild(cueCell(cuePoint.review_status));
    row.appendChild(cueActionsCell(row, cuePoint));
    cueRowsEl.appendChild(row);
  }
}

function cueCell(value) {
  const cell = document.createElement("td");
  cell.textContent = valueOrDash(value);
  return cell;
}

function cueLabelCell(cuePoint) {
  const cell = document.createElement("td");
  const label = document.createElement("span");
  label.className = "cueLabelText";
  label.textContent = valueOrDash(cuePoint.cue_label);
  cell.appendChild(label);
  return cell;
}

function cueActionsCell(row, cuePoint) {
  const cell = document.createElement("td");
  const editBtn = document.createElement("button");
  editBtn.className = "cueEditBtn secondaryButton";
  editBtn.type = "button";
  editBtn.title = "Rename cue";
  editBtn.setAttribute("aria-label", "Rename cue");
  editBtn.innerHTML = "&#9998;";

  editBtn.addEventListener("click", () => {
    startCueRename(row, cuePoint.id, editBtn);
  });

  cell.appendChild(editBtn);
  return cell;
}

function startCueRename(row, cueId, editBtn) {
  const labelCell = row.cells[1];
  const labelSpan = labelCell.querySelector(".cueLabelText");
  const currentLabel = labelSpan.textContent === "-" ? "" : labelSpan.textContent;

  const input = document.createElement("input");
  input.className = "cueLabelInput";
  input.value = currentLabel;
  input.setAttribute("aria-label", "New cue name");

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "cueRenameSave";
  saveBtn.textContent = "Save";

  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "secondaryButton cueRenameCancel";
  cancelBtn.textContent = "Cancel";

  const actionsCell = row.cells[6];

  labelSpan.hidden = true;
  labelCell.appendChild(input);
  editBtn.hidden = true;
  actionsCell.appendChild(saveBtn);
  actionsCell.appendChild(cancelBtn);
  input.focus();
  input.select();

  function finishRename() {
    labelSpan.hidden = false;
    input.remove();
    saveBtn.remove();
    cancelBtn.remove();
    editBtn.hidden = false;
  }

  cancelBtn.addEventListener("click", finishRename);

  saveBtn.addEventListener("click", async () => {
    const newLabel = input.value.trim();
    if (!newLabel) {
      input.focus();
      return;
    }
    saveBtn.disabled = true;
    cancelBtn.disabled = true;
    try {
      const response = await fetch(`/api/cue-points/${cueId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cue_label: newLabel }),
      });
      if (!response.ok) {
        const err = await responseErrorMessage(response, "Rename failed");
        labelCell.querySelector(".cueLabelText").hidden = false;
        input.remove();
        saveBtn.remove();
        cancelBtn.remove();
        editBtn.hidden = false;
        editBtn.title = err;
        return;
      }
      const result = await response.json();
      labelSpan.textContent = result.cue_point.cue_label;
      finishRename();
    } catch {
      finishRename();
    }
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") saveBtn.click();
    if (e.key === "Escape") cancelBtn.click();
  });
}

async function saveTrack(row, forcedStatus = null) {
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
  cell.colSpan = 6;
  cell.textContent = message;
  row.appendChild(cell);
  rowsEl.appendChild(row);
}

function renderCueTableMessage(message) {
  cueRowsEl.innerHTML = "";
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = 6;
  cell.textContent = message;
  row.appendChild(cell);
  cueRowsEl.appendChild(row);
}

function formatSeconds(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return String(value);
  }
  return `${numeric.toFixed(3)}s`;
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
 * Cue editor: waveform, transport, metronome, and 8 cue pads.
 * Audio is fetched once and decoded with the Web Audio API, so playback and
 * the waveform come from the same buffer. Audio files are never modified.
 * ------------------------------------------------------------------------ */

let audioCtx = null;
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

playButton.addEventListener("click", togglePlay);
stopButton.addEventListener("click", stopPlayback);
autoFillPadsButton.addEventListener("click", autoFillPads);
metronomeToggle.addEventListener("change", () => {
  if (metronomeToggle.checked && isPlaying) {
    startMetronome();
  } else {
    stopMetronome();
  }
});
waveformCanvas.addEventListener("click", (event) => {
  if (!audioBuffer || duration <= 0) return;
  const rect = waveformCanvas.getBoundingClientRect();
  seek(((event.clientX - rect.left) / rect.width) * duration);
});
window.addEventListener("resize", () => {
  if (selectedTrack) drawWaveform();
});

function getAudioContext() {
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
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

  editorTrackName.textContent = track.file_name || track.file_path || "Track";
  editorTrackMeta.textContent = [track.artist, track.title].filter(Boolean).join(" — ");
  editorBpm.textContent = track.bpm ? `BPM ${Number(track.bpm).toFixed(1)}` : "BPM —";
  autoFillPadsButton.disabled = false;

  await loadPads(track.id);
  await loadAudio(track);
}

async function loadAudio(track) {
  playButton.disabled = true;
  stopButton.disabled = true;
  editorTime.textContent = "Loading audio…";
  try {
    const response = await fetch(`/api/audio?path=${encodeURIComponent(track.file_path)}`);
    if (!response.ok) throw new Error("audio load failed");
    const arrayBuffer = await response.arrayBuffer();
    audioBuffer = await getAudioContext().decodeAudioData(arrayBuffer);
    duration = audioBuffer.duration;
    playButton.disabled = false;
    stopButton.disabled = false;
    drawWaveform();
    updateTime();
    renderPads();
  } catch (error) {
    audioBuffer = null;
    editorTime.textContent = "Audio unavailable";
    drawWaveform();
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
  sourceNode.connect(ctx.destination);
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
  drawWaveform();
  updateTime();
}

function stopPlayback() {
  stopSource();
  isPlaying = false;
  playStartOffset = 0;
  playButton.textContent = "▶ Play";
  stopMetronome();
  stopRAF();
  drawWaveform();
  updateTime();
}

function stopSource() {
  if (sourceNode) {
    sourceNode.onended = null;
    try {
      sourceNode.stop();
    } catch (error) {
      // already stopped
    }
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
  drawWaveform();
  updateTime();
}

function seek(position) {
  const clamped = Math.max(0, Math.min(position, duration));
  if (isPlaying) {
    startPlaybackFrom(clamped);
  } else {
    playStartOffset = clamped;
    drawWaveform();
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
  drawWaveform();
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
  const gain = ctx.createGain();
  osc.frequency.value = 1600;
  gain.gain.setValueAtTime(0.0001, when);
  gain.gain.exponentialRampToValueAtTime(0.4, when + 0.001);
  gain.gain.exponentialRampToValueAtTime(0.0001, when + 0.05);
  osc.connect(gain).connect(ctx.destination);
  osc.start(when);
  osc.stop(when + 0.06);
}

/* ---- Waveform ---- */

function drawWaveform() {
  const canvas = waveformCanvas;
  const cssWidth = canvas.clientWidth || 800;
  const cssHeight = 120;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = cssWidth * dpr;
  canvas.height = cssHeight * dpr;
  const ctx2d = canvas.getContext("2d");
  ctx2d.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx2d.clearRect(0, 0, cssWidth, cssHeight);
  ctx2d.fillStyle = "#eef2f5";
  ctx2d.fillRect(0, 0, cssWidth, cssHeight);

  if (audioBuffer) {
    const peaks = computePeaks(audioBuffer, cssWidth);
    const mid = cssHeight / 2;
    ctx2d.fillStyle = "#0f766e";
    for (let x = 0; x < peaks.length; x++) {
      const top = mid + peaks[x].min * mid;
      const bottom = mid + peaks[x].max * mid;
      ctx2d.fillRect(x, top, 1, Math.max(1, bottom - top));
    }
  } else {
    ctx2d.fillStyle = "#5f6b7a";
    ctx2d.font = "13px sans-serif";
    ctx2d.fillText("No waveform loaded", 10, 24);
  }

  if (duration > 0) {
    for (const pad of padsData) {
      if (pad.timestamp_seconds == null) continue;
      const x = (pad.timestamp_seconds / duration) * cssWidth;
      ctx2d.fillStyle = "#a33a3a";
      ctx2d.fillRect(x, 0, 2, cssHeight);
      ctx2d.font = "10px sans-serif";
      ctx2d.fillText(String(pad.pad_index + 1), x + 3, 11);
    }
    const playheadX = (currentPosition() / duration) * cssWidth;
    ctx2d.fillStyle = "#2563eb";
    ctx2d.fillRect(playheadX, 0, 2, cssHeight);
  }
}

function computePeaks(buffer, width) {
  const data = buffer.getChannelData(0);
  const samplesPerBucket = Math.floor(data.length / width) || 1;
  const peaks = [];
  for (let i = 0; i < width; i++) {
    let min = 1.0;
    let max = -1.0;
    const start = i * samplesPerBucket;
    const end = Math.min(start + samplesPerBucket, data.length);
    for (let j = start; j < end; j++) {
      const value = data[j];
      if (value < min) min = value;
      if (value > max) max = value;
    }
    if (min > max) {
      min = 0;
      max = 0;
    }
    peaks.push({ min, max });
  }
  return peaks;
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
  drawWaveform();
  padState.textContent = padsData.some((pad) => pad.timestamp_seconds != null)
    ? ""
    : "No pad positions yet — Auto-fill or Set from the playhead";
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
      if (pad.timestamp_seconds != null) startPlaybackFrom(pad.timestamp_seconds);
    });

    el.querySelector(".padSet").addEventListener("click", () => setPadFromPlayhead(pad.pad_index));
    el.querySelector(".padRename").addEventListener("click", () => renamePad(el, pad));

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

async function autoFillPads() {
  if (!selectedTrack) return;
  autoFillPadsButton.disabled = true;
  padState.textContent = "Auto-filling…";
  try {
    const response = await fetch(`/api/tracks/${selectedTrack.id}/pads/auto-fill`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!response.ok) {
      padState.textContent = await responseErrorMessage(response, "Auto-fill failed");
      return;
    }
    const payload = await response.json();
    padsData = payload.pads || [];
    renderPads();
    drawWaveform();
    padState.textContent = "Pads filled from phrasing";
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
