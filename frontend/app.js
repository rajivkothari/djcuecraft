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
  return row;
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
    row.appendChild(cueCell(cuePoint.file_name || cuePoint.file_path));
    row.appendChild(cueCell(cuePoint.cue_label));
    row.appendChild(cueCell(cuePoint.beat_index));
    row.appendChild(cueCell(formatSeconds(cuePoint.timestamp_seconds)));
    row.appendChild(cueCell(formatConfidence(cuePoint.cue_confidence)));
    row.appendChild(cueCell(cuePoint.review_status));
    cueRowsEl.appendChild(row);
  }
}

function cueCell(value) {
  const cell = document.createElement("td");
  cell.textContent = valueOrDash(value);
  return cell;
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
