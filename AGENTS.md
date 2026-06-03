# Agent Notes

DJ CueCraft is a local-first DJ library preparation app.

Hard constraints:

- Do not mutate audio files without explicit user approval.
- Keep every metadata change reviewable before write-back.
- Treat Indian and Latin genre tags cautiously.
- Keep Phase 1 focused on scanning, metadata reading, SQLite storage, and proposed normalization.
- Do not add cloud services, login, payment, DJ performance features, external API lookups, BPM detection, cue writing, or direct DJ database editing.

Preferred engineering style:

- Use simple, testable Python modules.
- Keep database writes limited to local app records.
- Add focused tests before expanding behavior.
- Preserve future space for a Tauri/React or Electron/React frontend.

