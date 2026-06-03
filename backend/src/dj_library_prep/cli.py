from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from dj_library_prep import database
from dj_library_prep.beat_analyzer import BeatCueAnalysisSummary, analyze_beats_for_folder
from dj_library_prep.bpm_analyzer import BpmAnalysisSummary, analyze_bpm_for_folder
from dj_library_prep.correction_importer import CorrectionImportSummary, import_corrections
from dj_library_prep.cue_exporter import export_cue_points_to_csv
from dj_library_prep.csv_exporter import export_tracks_to_csv
from dj_library_prep.genre_normalizer import normalize_track_fields
from dj_library_prep.metadata import read_track_metadata
from dj_library_prep.models import ReviewStatus, Track
from dj_library_prep.scanner import scan_audio_files


@dataclass(frozen=True, slots=True)
class ScanSummary:
    total_tracks_scanned: int
    tracks_with_metadata: int
    tracks_with_normalized_genre_suggestions: int
    tracks_needing_review: int
    missing_artist: int
    missing_title: int
    missing_year: int
    missing_genre: int


def scan_folder(folder: str | Path, database_path: str | Path) -> ScanSummary:
    audio_files = scan_audio_files(folder)
    tracks = [_prepare_track(path) for path in audio_files]

    with database.connect(database_path) as connection:
        database.save_tracks(connection, tracks)

    return summarize_tracks(tracks)


def summarize_tracks(tracks: list[Track]) -> ScanSummary:
    return ScanSummary(
        total_tracks_scanned=len(tracks),
        tracks_with_metadata=sum(1 for track in tracks if track.metadata_confidence > 0),
        tracks_with_normalized_genre_suggestions=sum(
            1 for track in tracks if track.normalized_primary_genre
        ),
        tracks_needing_review=sum(
            1 for track in tracks if track.review_status == ReviewStatus.NEEDS_REVIEW
        ),
        missing_artist=sum(1 for track in tracks if not track.artist),
        missing_title=sum(1 for track in tracks if not track.title),
        missing_year=sum(1 for track in tracks if not track.year),
        missing_genre=sum(1 for track in tracks if not track.original_genre),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dj-library-prep")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Scan a local music folder")
    scan_parser.add_argument("folder", help="Folder containing local audio files")
    scan_parser.add_argument(
        "--database",
        default="djcuecraft.sqlite3",
        help="SQLite database path. Defaults to djcuecraft.sqlite3",
    )

    export_parser = subparsers.add_parser(
        "export-csv",
        help="Export scanned tracks and proposed normalized tags to CSV",
    )
    export_parser.add_argument(
        "--database",
        default="djcuecraft.sqlite3",
        help="SQLite database path. Defaults to djcuecraft.sqlite3",
    )
    export_parser.add_argument(
        "--output",
        required=True,
        help="CSV output path",
    )

    import_parser = subparsers.add_parser(
        "import-corrections",
        help="Import manually corrected normalized genre fields from CSV",
    )
    import_parser.add_argument(
        "csv_path",
        help="Corrected CSV file exported from export-csv",
    )
    import_parser.add_argument(
        "--database",
        default="djcuecraft.sqlite3",
        help="SQLite database path. Defaults to djcuecraft.sqlite3",
    )

    bpm_parser = subparsers.add_parser(
        "analyze-bpm",
        help="Experimentally detect BPM values and store them in SQLite",
    )
    bpm_parser.add_argument("folder", help="Folder containing local audio files")
    bpm_parser.add_argument(
        "--database",
        default="djcuecraft.sqlite3",
        help="SQLite database path. Defaults to djcuecraft.sqlite3",
    )

    beat_parser = subparsers.add_parser(
        "analyze-beats",
        help="Experimentally detect beat positions and propose cue points",
    )
    beat_parser.add_argument("folder", help="Folder containing local audio files")
    beat_parser.add_argument(
        "--database",
        default="djcuecraft.sqlite3",
        help="SQLite database path. Defaults to djcuecraft.sqlite3",
    )

    cue_export_parser = subparsers.add_parser(
        "export-cues-csv",
        help="Export proposed cue points to CSV",
    )
    cue_export_parser.add_argument(
        "--database",
        default="djcuecraft.sqlite3",
        help="SQLite database path. Defaults to djcuecraft.sqlite3",
    )
    cue_export_parser.add_argument(
        "--output",
        required=True,
        help="CSV output path",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        summary = scan_folder(args.folder, args.database)
        _print_summary(summary)
        return 0

    if args.command == "export-csv":
        exported_count = export_tracks_to_csv(args.database, args.output)
        print(f"Exported {exported_count} tracks to {args.output}")
        print("No audio files were modified.")
        return 0

    if args.command == "import-corrections":
        summary = import_corrections(args.csv_path, args.database)
        _print_import_summary(summary)
        return 0

    if args.command == "analyze-bpm":
        summary = analyze_bpm_for_folder(args.folder, args.database)
        _print_bpm_summary(summary)
        return 0

    if args.command == "analyze-beats":
        summary = analyze_beats_for_folder(args.folder, args.database)
        _print_beat_summary(summary)
        return 0

    if args.command == "export-cues-csv":
        exported_count = export_cue_points_to_csv(args.database, args.output)
        print(f"Exported {exported_count} cue points to {args.output}")
        print("No audio files or DJ software libraries were modified.")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def _prepare_track(path: Path) -> Track:
    track = read_track_metadata(path)
    genre, decade = normalize_track_fields(
        track.original_genre,
        track.year,
        artist=track.artist,
        title=track.title,
        file_name=track.file_name,
    )
    track.normalized_decade = decade
    track.normalized_primary_genre = genre.primary_genre
    track.normalized_subgenre = genre.subgenre
    track.dj_use_tags = genre.dj_use_tags
    track.genre_confidence = genre.confidence
    track.review_status = genre.review_status
    if track.missing_fields():
        track.review_status = ReviewStatus.NEEDS_REVIEW
    return track


def _print_summary(summary: ScanSummary) -> None:
    print("Scan summary")
    print(f"  total tracks scanned: {summary.total_tracks_scanned}")
    print(f"  tracks with metadata: {summary.tracks_with_metadata}")
    print(
        "  tracks with normalized genre suggestions: "
        f"{summary.tracks_with_normalized_genre_suggestions}"
    )
    print(f"  tracks needing review: {summary.tracks_needing_review}")
    print(f"  missing artist: {summary.missing_artist}")
    print(f"  missing title: {summary.missing_title}")
    print(f"  missing year: {summary.missing_year}")
    print(f"  missing genre: {summary.missing_genre}")


def _print_import_summary(summary: CorrectionImportSummary) -> None:
    print("Correction import summary")
    print(f"  rows read: {summary.rows_read}")
    print(f"  updated tracks: {summary.updated_tracks}")
    print(f"  unchanged tracks: {summary.unchanged_tracks}")
    print(f"  skipped missing tracks: {summary.skipped_missing_tracks}")
    print("No audio files were modified.")


def _print_bpm_summary(summary: BpmAnalysisSummary) -> None:
    print("BPM analysis summary")
    print(f"  total files: {summary.total_files}")
    print(f"  analyzed tracks: {summary.analyzed_tracks}")
    print(f"  tracks needing review: {summary.tracks_needing_review}")
    print(f"  failed tracks: {summary.failed_tracks}")
    print("No audio files were modified.")


def _print_beat_summary(summary: BeatCueAnalysisSummary) -> None:
    print("Beat and cue analysis summary")
    print(f"  total files: {summary.total_files}")
    print(f"  analyzed tracks: {summary.analyzed_tracks}")
    print(f"  stored beats: {summary.stored_beats}")
    print(f"  proposed cue points: {summary.proposed_cue_points}")
    print(f"  cue points needing review: {summary.cue_points_needing_review}")
    print(f"  failed tracks: {summary.failed_tracks}")
    print("No audio files or DJ software libraries were modified.")


if __name__ == "__main__":
    raise SystemExit(main())
