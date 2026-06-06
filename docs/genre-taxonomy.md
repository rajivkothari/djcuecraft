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
- Pop
- Dance
- Freestyle
- Country
- Latin
- Indian
- Reggae-Dancehall

Optional subgenres are used when the source tag is specific enough:

**Hip-Hop**: Pop Rap, Club Rap, Trap, Boom Bap

**R&B**: Contemporary R&B, Soul, Funk, New Jack Swing

**Pop**: Pop, Dance Pop

**Dance**: House, EDM

**Freestyle**: Club Freestyle, Latin Freestyle

**Country**: Country, Country Rock

**Latin**: Salsa, Bachata, Cumbia, Reggaeton, Dembow, Merengue

**Indian**: Bollywood Dance, Classic Bollywood, Hindi, Punjabi-Bhangra, Punjabi Pop, Tamil, Tamil-Kollywood, Tamil Dance, Telugu, Marathi, Gujarati, Rajasthani

## Rule Format

Each rule supports:

- `field`: `genre`, `artist`, `title`, `file_name`, or `keyword`
- `match_type`: `exact` or `contains`
- `values`: case-insensitive match values
- `normalized_primary_genre`
- `normalized_subgenre`
- `dj_use_tags`
- `requires_context`: optional list of terms — rule only fires when at least one appears in any metadata field
- `context_subgenre`: subgenre override used when `requires_context` terms are present
- `confidence`
- `review_status`

`keyword` rules search across genre, artist, title, and filename. Utility tag rules can add `dj_use_tags` such as `clean`, `explicit`, `intro`, or `remix-edit` without replacing the selected normalized genre.

When multiple genre rules match, the highest-confidence genre rule wins. This allows a specific rule such as `Reggaeton` to beat a broad rule such as `Latin`.

### Context-Sensitive Rules (`requires_context`)

Some rules fire only when additional context is detected in the track's metadata. For example:

- `genre-hip-hop-club-rap`: fires when genre contains "hip-hop" or "rap" AND title/filename contains "club", "party", "anthem", or "dance floor" → Hip-Hop / Club Rap (0.93)
- `genre-bollywood-dance`: fires when genre is "Bollywood" AND context contains "dance", "club", "wedding", "remix", or "edit" → Indian / Bollywood Dance (0.80)
- `genre-freestyle-latin`: fires when genre is "Freestyle" AND context contains "latin" → Freestyle / Latin Freestyle (0.80)
- `genre-pop-dance-context`: fires when genre is "Pop" AND context contains "dance", "club", "remix", or "edit" → Pop / Dance Pop (0.80)

Context-sensitive rules have slightly higher confidence than their base siblings so they win when context is present.

## Indian Music Caution Notes

Indian music tags can describe language, film industry, region, era, or style. Broad tags such as `Indian` are low confidence and require review. Tags such as `Bollywood`, `Punjabi`, `Bhangra`, or `Tamil` can receive more specific proposals, but they still remain reviewable.

**Hindi is a language tag, not a film industry.** It maps to `Indian / Hindi` with confidence 0.55 and is always marked `needs_review` — it does not imply Bollywood.

**Punjabi** is a broad language/regional tag that could be bhangra, pop, or folk. It maps to `Indian / Punjabi-Bhangra` with confidence 0.55 and `needs_review`. Use `Bhangra` for a more confident mapping, or `Punjabi Pop` for pop context.

**Bollywood** maps to `Indian / Bollywood Dance` when dance/club/wedding/remix context is present, or `Indian / Classic Bollywood` otherwise. Both are confident mappings (0.80 / 0.78, pending).

Regional language tags (Tamil, Telugu, Marathi, Gujarati, Rajasthani) map to `Indian / <tag>` with confidence 0.55 and `needs_review` because they describe language/region, not style.

Filename and keyword rules such as `bollywood` or `desi` are intentionally lower confidence and default to `needs_review` because they are often useful clues rather than reliable genre proof.

## Latin Music Caution Notes

Latin music tags can describe a broad region, rhythm, language, or scene. Broad tags such as `Latin` are low confidence and require review. Specific tags such as `Salsa`, `Bachata`, `Cumbia`, `Merengue`, and `Reggaeton` receive more useful proposals.

Keyword rules such as `Dembow` are useful but still marked `needs_review` unless the embedded metadata is specific enough.

## Confidence Scoring Logic

- Clear mainstream mappings receive higher confidence.
- Context-sensitive rules beat their base siblings via slightly higher confidence values.
- Specific Latin and Indian subgenre mappings receive moderate confidence.
- Broad labels such as `World`, `Soundtrack`, `International`, `Indian`, or `Latin` receive lower confidence and are marked `needs_review`.
- Language/regional tags (Hindi, Punjabi, Tamil, Telugu, Marathi, etc.) are always `needs_review` because they indicate cultural context, not style.
- Artist, filename, and keyword clues usually receive lower confidence than embedded exact genre tags.
- Missing or unknown genre tags are marked `needs_review`.
- Tracks without a year tag always produce `review_required = True` in metadata suggestions.
