# Product Brief

## Product Purpose

DJ CueCraft helps DJs prepare music libraries before performance by safely scanning tracks, reading metadata, and proposing cleanup actions that can be reviewed.

## Target User

The primary user is a working DJ or serious hobbyist with a local collection that includes mixed genres, eras, and regional catalogs.

## Core Pain Point

DJs spend too much time manually cleaning inconsistent genre tags, decade labels, and incomplete metadata. Mistakes are expensive because bad tags can make tracks hard to find during a set.

## MVP Boundaries

Phase 1 focuses on local scanning, metadata extraction, SQLite storage, rule-based genre normalization, decade normalization, review status tracking, CSV review workflows, experimental BPM and beat analysis, cue point proposals, and a minimal local review UI.

The app does not write changes back to audio files, DJ software databases, or cloud services in Phase 1. All cleanup results remain local SQLite records or exported review files.

## Current Implementation

- Folder scanning for supported local audio files.
- Embedded metadata reading.
- SQLite persistence for tracks, review history, correction history, BPM values, beat timestamps, and cue point proposals.
- Rule-based genre and decade normalization.
- CSV export and CSV correction import.
- Experimental BPM detection.
- Experimental beat timestamp storage and cue point proposals.
- Minimal browser-based local review UI.

## Future Features

- Safe metadata write-back with backups.
- MusicBrainz or AcoustID lookup.
- Improved BPM, beat-grid, and cue point accuracy.
- Dedicated cue point review workflow.
- Export adapters for DJ library ecosystems.
- Desktop wrapper with Tauri or Electron.

