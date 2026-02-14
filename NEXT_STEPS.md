# Polish Vocabulary Extractor: Next Steps

This document expands three practical directions for the app and gives a step-by-step implementation walkthrough for each.

---

## 1. Accuracy Hardening (Lemmatization + Cleaning Profiles)

### Goal
Improve word quality in output by reducing bad lemmas and source-noise tokens.

### Why this matters
- Better lemmas means cleaner frequency lists.
- Better cleaning means less menu/footer/UI garbage from scraped pages.
- Accuracy gains compound across every other feature.

### Scope
1. Add source cleaning profiles.
2. Add lemma diagnostics.
3. Add manual overrides for recurring bad mappings.

### Walkthrough
1. Introduce cleaning profiles in `config.json`.
   - Add named profiles, for example `realpolish`, `generic_wp`.
   - Each profile contains `start`, `end`, and optional selectors to drop.
2. Update `extractor/cleaner.py` to accept `profile_name`.
   - Resolve profile.
   - Apply profile-specific trimming/decomposition.
3. Add lemma diagnostics mode in pipeline.
   - Emit a report `token -> lemma -> count`.
   - Include flags for suspicious lemmas (e.g., very low zipf, non-dictionary-looking endings).
4. Add override map support.
   - Create `data/lemma_overrides.json`.
   - Apply override after auto-lemmatization, before counting.
5. Surface overrides in GUI.
   - Add “Use lemma overrides” checkbox.
   - Add button “Open override file”.
6. Add tests.
   - Golden tests for known phrases and expected lemmas.
   - HTML cleaning tests for representative documents.

### Deliverables
- Profile-driven cleaner.
- Lemma diagnostics report.
- Optional override system.
- Regression tests for core mapping behavior.

---

## 2. Learning Output Pipeline

### Goal
Turn extraction output into study-ready artifacts (not just ranked lists).

### Why this matters
- Extraction is only half the workflow.
- Users want immediate artifacts for Anki, review sheets, and lesson plans.

### Scope
1. Multi-format export (`HTML`, `CSV`, `TSV`).
2. Optional learning metadata columns.
3. Output templates for different use cases.

### Walkthrough
1. Standardize internal result schema.
   - Reuse `Row` in `app_logic.py`.
   - Add optional fields: `example`, `note`, `translation`.
2. Add exporter module `extractor/export.py`.
   - `to_html(rows, path)`.
   - `to_csv(rows, path)`.
   - `to_tsv(rows, path)`.
3. Add Anki-friendly export mode.
   - Fixed column order: `Front`, `Back`, `Tags`.
   - Use lemma as front; forms/examples as back.
4. Add GUI export options.
   - Checkboxes for output types.
   - Output directory picker.
5. Add optional dictionary/gloss integration (later phase).
   - Keep async and cached.
   - Ensure failures degrade gracefully.
6. Add validation.
   - Snapshot tests for HTML table.
   - CSV compatibility tests (encoding + delimiter correctness).

### Deliverables
- Export module with multiple formats.
- GUI export controls.
- Anki-ready output path.

---

## 3. Usability + Reliability

### Goal
Make the app robust for daily use, easier to debug, and easier to trust.

### Why this matters
- Stable UX reduces support overhead.
- Better diagnostics shorten debugging loops.
- Session persistence makes repeat usage faster.

### Scope
1. Persist user settings.
2. Improve run diagnostics.
3. Add run history + reproducibility data.

### Walkthrough
1. Add persistent settings file.
   - Create `data/gui_settings.json`.
   - Save start/end markers, options, limit, last output dir.
2. Load settings on startup.
   - Validate schema and defaults.
   - Continue with safe fallback on parse error.
3. Improve progress and error reporting.
   - Emit step-level lifecycle events: `started`, `advanced`, `done`, `failed`.
   - Show current file and step in UI log.
4. Add structured run logs.
   - Write JSONL logs to `output_html/runs/`.
   - Store config snapshot + file hashes + runtime stats.
5. Add crash-safe reporting.
   - Catch worker exceptions.
   - Include traceback and file context in log and UI dialog.
6. Add smoke tests.
   - End-to-end CLI smoke test on a known input fixture.
   - Basic GUI integration check for run flow (headless-safe where possible).

### Deliverables
- Persistent settings.
- Better progress and diagnostics.
- Reproducible run history.

---

## Suggested Implementation Order

1. Accuracy hardening.
2. Usability + reliability.
3. Learning output pipeline.

This order gives better data first, then stabilizes operation, then scales output formats.

---

## Time/Effort Estimate (Rough)

| Track | Effort | Risk | Impact |
|---|---:|---:|---:|
| Accuracy hardening | 2-4 days | Medium | High |
| Usability + reliability | 1-3 days | Low-Medium | High |
| Learning output pipeline | 2-5 days | Medium | High |

