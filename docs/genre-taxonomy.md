# Genre Taxonomy

## DJ-Friendly Taxonomy

Phase 1 normalizes common tags into a smaller DJ-friendly taxonomy. Rules live in editable JSON files under `backend/src/dj_library_prep/rules/`:

- `general_genres.json`
- `latin_music.json`
- `indian_music.json`
- `dj_utility_tags.json`

The engine can evaluate embedded genre, artist, title, filename, and keyword context.

Current primary genres include:

- Hip-Hop
- R&B
- Disco
- Funk
- Latin
- Indian

Optional subgenres are used when the source tag is specific enough, such as Salsa, Bachata, Cumbia, Reggaeton, Bollywood, Punjabi-Bhangra, or Tamil.

## Rule Format

Each rule supports:

- `field`: `genre`, `artist`, `title`, `file_name`, or `keyword`
- `match_type`: `exact` or `contains`
- `values`: case-insensitive match values
- `normalized_primary_genre`
- `normalized_subgenre`
- `dj_use_tags`
- `confidence`
- `review_status`

`keyword` rules search across genre, artist, title, and filename. Utility tag rules can add `dj_use_tags` such as `clean`, `explicit`, `intro`, or `remix-edit` without replacing the selected normalized genre.

When multiple genre rules match, the highest-confidence genre rule wins. This allows a specific rule such as `Reggaeton` to beat a broad rule such as `Latin`.

## Indian Music Caution Notes

Indian music tags can describe language, film industry, region, era, or style. Broad tags such as `Indian` are low confidence and require review. Tags such as `Bollywood`, `Punjabi`, `Bhangra`, or `Tamil` can receive more specific proposals, but they still remain reviewable.

Filename and keyword rules such as `bollywood` or `desi` are intentionally lower confidence and default to `needs_review` because they are often useful clues rather than reliable genre proof.

## Latin Music Caution Notes

Latin music tags can describe a broad region, rhythm, language, or scene. Broad tags such as `Latin` are low confidence and require review. Specific tags such as `Salsa`, `Bachata`, `Cumbia`, and `Reggaeton` receive more useful proposals.

Keyword rules such as `Dembow` are useful but still marked `needs_review` unless the embedded metadata is specific enough.

## Confidence Scoring Logic

- Clear mainstream mappings receive higher confidence.
- Specific Latin and Indian subgenre mappings receive moderate confidence.
- Broad labels such as `World`, `Soundtrack`, `International`, `Indian`, or `Latin` receive lower confidence and are marked `needs_review`.
- Artist, filename, and keyword clues usually receive lower confidence than embedded exact genre tags.
- Missing or unknown genre tags are marked `needs_review`.
