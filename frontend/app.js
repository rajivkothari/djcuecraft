const rowsEl = document.querySelector("#trackRows");
const template = document.querySelector("#trackRowTemplate");
const summaryEl = document.querySelector("#summary");
const statusFilter = document.querySelector("#statusFilter");
const refreshButton = document.querySelector("#refreshButton");

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

  row.querySelector('[data-action="save"]').addEventListener("click", () => {
    saveTrack(row);
  });
  row.querySelector('[data-action="history"]').addEventListener("click", () => {
    loadHistory(row);
  });
  return row;
}

async function saveTrack(row) {
  const trackId = row.dataset.trackId;
  const saveButton = row.querySelector('[data-action="save"]');
  const rowState = row.querySelector('[data-field="row_state"]');
  const payload = {};

  for (const field of editableFields) {
    payload[field] = row.querySelector(`[data-input="${field}"]`).value;
  }

  saveButton.disabled = true;
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
    rowState.textContent = "Saved";
  } catch (error) {
    rowState.textContent = "Save failed";
  } finally {
    saveButton.disabled = false;
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
      item.textContent = `${record.timestamp} ${record.source}: ${record.previous_review_status} -> ${record.new_review_status}; ${valueOrDash(record.previous_normalized_primary_genre)} -> ${valueOrDash(record.new_normalized_primary_genre)}`;
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

async function responseErrorMessage(response, fallback) {
  try {
    const error = await response.json();
    return error.error || fallback;
  } catch (error) {
    return fallback;
  }
}
