from __future__ import annotations

import threading
import traceback
from collections import Counter
from pathlib import Path

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from app_logic import Settings, apply_ignore_patterns, build_rows, render_html
from app_logic import (
    apply_translations_to_clozemaster_entries,
    append_unique_clozemaster_entries,
    build_clozemaster_entries,
    split_sentences,
)
from extractor.translation import OpusMtTranslator
from extractor.cleaner import extract_text
from extractor.tokenizer import lemma_groups, tokenize
from extractor.youtube import fetch_youtube_caption_text

from .helpers import coerce_path, iter_paths_from_drop


class RunMixin:
    def _refresh_sources_display(self) -> None:
        lines: list[str] = [str(p) for p in self.files]
        lines.extend(f"[YouTube] {link}" for link in getattr(self, "youtube_links", []))
        self.file_list.value = "\n".join(lines)

    def start(self, _widget) -> None:
        # Compatibility path for tests/older hooks.
        self.start_tokenize(_widget)

    async def browse(self, _widget) -> None:
        try:
            result = await self.main_window.dialog(
                toga.OpenFileDialog("Select files", multiple_select=True)
            )
        except Exception as exc:
            self.logger.exception("Browse dialog failed")
            self.main_window.error_dialog("Browse failed", str(exc))
            return

        if not result:
            return
        for p in result:
            path = coerce_path(p)
            if path is not None:
                self._add_file(path)

    def open_youtube_links_window(self, _widget) -> None:
        existing_window = getattr(self, "_youtube_window", None)
        if existing_window is not None:
            existing_window.show()
            return

        default_text = "\n".join(getattr(self, "youtube_links", []))
        self._youtube_links_input = toga.MultilineTextInput(
            value=default_text,
            placeholder="Paste one YouTube URL per row",
            style=Pack(flex=1, height=220),
        )
        info = toga.Label(
            "Add one URL per line. Captions download is not implemented yet."
        )
        save_btn = toga.Button(
            "Save links",
            on_press=self._save_youtube_links,
            style=Pack(margin_top=8),
        )
        close_btn = toga.Button(
            "Cancel",
            on_press=self._close_youtube_links_window,
            style=Pack(margin_top=8, margin_left=8),
        )
        actions = toga.Box(style=Pack(direction=ROW))
        actions.add(save_btn)
        actions.add(close_btn)

        content = toga.Box(style=Pack(direction=COLUMN, margin=12))
        content.add(info)
        content.add(self._youtube_links_input)
        content.add(actions)

        self._youtube_window = toga.MainWindow(title="YouTube Links")
        self._youtube_window.content = content
        self._youtube_window.size = (700, 420)
        self._youtube_window.show()

    def _save_youtube_links(self, _widget) -> None:
        raw = (getattr(self, "_youtube_links_input", None).value or "")
        links = [line.strip() for line in raw.splitlines() if line.strip()]
        self.youtube_links = links
        self._refresh_sources_display()
        self._append_log(f"Saved YouTube links: {len(links)}")
        window = getattr(self, "_youtube_window", None)
        if window is not None:
            window.close()
            self._youtube_window = None

    def _close_youtube_links_window(self, _widget) -> None:
        window = getattr(self, "_youtube_window", None)
        if window is None:
            return
        window.close()
        self._youtube_window = None

    def on_drop(self, *args) -> None:
        for path in iter_paths_from_drop(*args):
            if path.is_file():
                self._add_file(path)

    def _add_file(self, path: Path) -> None:
        if path in self.files:
            return
        self.files.append(path)
        self._refresh_sources_display()
        self._append_log(f"Added file: {path}")

    def clear_files(self, _widget) -> None:
        if self.is_running:
            self._append_log("Cannot clear file list while processing")
            return
        if not self.files:
            if not getattr(self, "youtube_links", []):
                return
        self.files.clear()
        links = getattr(self, "youtube_links", None)
        if links is None:
            self.youtube_links = []
        else:
            links.clear()
        self._refresh_sources_display()
        self.staged_results.clear()
        self.staged_sentences.clear()
        self._preview_terms_cache.clear()
        self._clear_zipf_examples()
        self._set_listing_controls_ready(False)
        self.export_btn.enabled = False
        if self.cancel_btn in self.tokenize_button_row.children:
            self.tokenize_button_row.remove(self.cancel_btn)
        self._refresh_preview()
        self._append_log("Cleared file list")

    def start_tokenize(self, _widget) -> None:
        self._debug("tokenize pressed", is_running=self.is_running, files=len(self.files))
        if self.is_running:
            return
        if not self.files and not getattr(self, "youtube_links", []):
            self.main_window.error_dialog("No files", "Please add at least one file.")
            return

        try:
            limit_value = int(self.limit_input.value or 50)
        except ValueError:
            self.main_window.error_dialog("Invalid limit", "Limit must be a number.")
            return

        settings = self._current_settings(limit_value=limit_value)
        out_dir = Path("output_html")
        out_dir.mkdir(exist_ok=True)
        self._append_log(
            f"Start tokenize: files={len(self.files)} limit={limit_value} "
            f"youtube_links={len(getattr(self, 'youtube_links', []))} "
            f"use_wordfreq={settings.use_wordfreq} allow_ones={settings.allow_ones} "
            f"allow_inflections={settings.allow_inflections} "
            f"min_zipf={settings.min_zipf:.1f} max_zipf={settings.max_zipf:.1f} "
            f"balance_a={settings.balance_a:.2f} "
            f"ignore_patterns={len(settings.ignore_patterns)}"
        )

        self.progress.value = 0
        self.progress.max = 1
        self.step_totals = {"clean": 1, "tokenize": 0, "lemmatize": 0, "count": 1}
        self.cancel_requested = False
        self.is_running = True
        self.tokenize_btn.enabled = False
        self.clear_files_btn.enabled = False
        self._set_listing_controls_ready(False)
        self._debug("run dispatch", mode="tokenize")
        self._run_tokenize_stage(settings)

    def start_export(self, _widget) -> None:
        self._debug(
            "export pressed",
            is_running=self.is_running,
            staged_files=len(self.staged_results),
        )
        if self.is_running:
            return
        if not self.staged_results:
            self.main_window.error_dialog(
                "Tokenization required",
                "Run Tokenize first to enable listing/export.",
            )
            return

        try:
            limit_value = int(self.limit_input.value or 50)
        except ValueError:
            self.main_window.error_dialog("Invalid limit", "Limit must be a number.")
            return

        settings = self._current_settings(limit_value=limit_value)
        out_dir = Path("output_html")
        out_dir.mkdir(exist_ok=True)
        self._append_log(
            f"Start export: staged_files={len(self.staged_results)} limit={limit_value} "
            f"allow_ones={settings.allow_ones} allow_inflections={settings.allow_inflections} "
            f"min_zipf={settings.min_zipf:.1f} max_zipf={settings.max_zipf:.1f} "
            f"balance_a={settings.balance_a:.2f} "
            f"translate_clozemaster={settings.translate_clozemaster} "
            f"translation_model={settings.translation_model}"
        )

        self.progress.value = 0
        self.progress.max = max(1, len(self.staged_results))
        self.cancel_requested = False
        self.is_running = True
        self.tokenize_btn.enabled = False
        self.clear_files_btn.enabled = False
        self._set_listing_controls_ready(False)
        self._debug("run dispatch", mode="rank")
        self._run_rank_stage(settings, out_dir)

    def _run_tokenize_stage(self, settings: Settings) -> None:
        self.staged_results.clear()
        self.staged_sentences.clear()
        self._preview_terms_cache.clear()
        self._append_log("Tokenize stage started")
        self._debug("tokenize stage init", files=len(self.files))

        def run() -> None:
            self._debug("tokenize stage thread start", files=len(self.files))

            def report(step: str, total: int | None, advance: int) -> None:
                def update() -> None:
                    if total is not None:
                        self.step_totals[step] = total
                        self.progress.max = sum(self.step_totals.values())
                    if advance:
                        self.progress.value = min(
                            self.progress.value + advance, self.progress.max
                        )

                self.main_window.app.loop.call_soon_threadsafe(update)

            try:
                for path in self.files:
                    if self.cancel_requested:
                        break
                    self.main_window.app.loop.call_soon_threadsafe(
                        lambda p=path: self._append_log(f"Tokenizing file: {p.name}")
                    )
                    report("clean", 1, 0)
                    text = extract_text(path, settings.start, settings.end)
                    report("clean", None, 1)
                    self.staged_sentences[path.name] = split_sentences(text)
                    tokens = tokenize(text, progress=lambda t, a: report("tokenize", t, a))
                    self._debug(
                        "tokenize tokens ready",
                        file=path.name,
                        token_count=len(tokens),
                        sentence_count=len(self.staged_sentences[path.name]),
                    )
                    tokens = apply_ignore_patterns(tokens, settings.ignore_patterns)
                    self._debug(
                        "tokenize ignore applied",
                        file=path.name,
                        token_count=len(tokens),
                        ignore_patterns=len(settings.ignore_patterns),
                    )
                    groups = lemma_groups(
                        tokens,
                        text=None,
                        progress=lambda t, a: report("lemmatize", t, a),
                    )
                    counts = Counter(tokens)
                    if not settings.allow_ones:
                        counts = Counter({k: v for k, v in counts.items() if v > 1})
                    self.staged_results[path.name] = (counts, groups)
                    self._debug(
                        "tokenize staged",
                        file=path.name,
                        token_types=len(counts),
                        lemmas=len(groups),
                    )

                for idx, url in enumerate(getattr(self, "youtube_links", []), start=1):
                    if self.cancel_requested:
                        break
                    source_name = f"youtube_{idx:03d}"
                    self.main_window.app.loop.call_soon_threadsafe(
                        lambda u=url: self._append_log(f"Fetching YouTube captions: {u}")
                    )
                    text = fetch_youtube_caption_text(url)
                    if not text.strip():
                        self.main_window.app.loop.call_soon_threadsafe(
                            lambda u=url: self._append_log(
                                f"No captions found for: {u}"
                            )
                        )
                        continue
                    self.staged_sentences[source_name] = split_sentences(text)
                    tokens = tokenize(text, progress=lambda t, a: report("tokenize", t, a))
                    self._debug(
                        "tokenize youtube tokens ready",
                        source=source_name,
                        token_count=len(tokens),
                        sentence_count=len(self.staged_sentences[source_name]),
                    )
                    tokens = apply_ignore_patterns(tokens, settings.ignore_patterns)
                    groups = lemma_groups(
                        tokens,
                        text=None,
                        progress=lambda t, a: report("lemmatize", t, a),
                    )
                    counts = Counter(tokens)
                    if not settings.allow_ones:
                        counts = Counter({k: v for k, v in counts.items() if v > 1})
                    self.staged_results[source_name] = (counts, groups)
                    self.main_window.app.loop.call_soon_threadsafe(
                        lambda n=source_name: self._append_log(
                            f"Tokenized YouTube source: {n}"
                        )
                    )
            except Exception as exc:
                tb = traceback.format_exc()
                self.logger.error("Tokenize stage failed: %s\n%s", exc, tb)
                self.main_window.app.loop.call_soon_threadsafe(
                    lambda e=exc: self.main_window.error_dialog(
                        "Tokenization failed", str(e)
                    )
                )
                self.main_window.app.loop.call_soon_threadsafe(self._finish_run)
                return

            def done() -> None:
                self._debug(
                    "tokenize done callback",
                    canceled=self.cancel_requested,
                    staged_files=len(self.staged_results),
                )
                if self.cancel_requested:
                    self._append_log("Tokenize stage canceled")
                    self.staged_results.clear()
                    self.staged_sentences.clear()
                    self._finish_run()
                    return
                self._append_log("Tokenize stage finished")
                self._rebuild_preview_cache()
                self._update_zipf_examples()
                self._refresh_preview()
                self._set_listing_controls_ready(True)
                if self.cancel_btn not in self.tokenize_button_row.children:
                    self.tokenize_button_row.add(self.cancel_btn)
                self._finish_run()

            self.main_window.app.loop.call_soon_threadsafe(done)

        threading.Thread(target=run, daemon=True).start()

    def _run_rank_stage(self, settings: Settings, out_dir: Path) -> None:
        self._append_log("Rank stage started")
        self._debug("rank stage init", staged_files=len(self.staged_results))

        def run() -> None:
            self._debug("rank stage thread start", staged_files=len(self.staged_results))
            results: dict[str, list] = {}
            clozemaster_entries: list[tuple[str, str, str, str, str]] = []
            total_files = max(1, len(self.staged_results))
            self.main_window.app.loop.call_soon_threadsafe(
                lambda: setattr(self.progress, "max", total_files)
            )
            self.main_window.app.loop.call_soon_threadsafe(
                lambda: setattr(self.progress, "value", 0)
            )

            try:
                for name, (counts, groups) in self.staged_results.items():
                    if self.cancel_requested:
                        break
                    rows = build_rows(counts, groups, settings)
                    self._debug("rank rows built", file=name, rows=len(rows))
                    results[name] = rows
                    clozemaster_entries.extend(
                        build_clozemaster_entries(
                            rows,
                            groups,
                            self.staged_sentences.get(name, []),
                            allow_inflections=settings.allow_inflections,
                        )
                    )
                    self.main_window.app.loop.call_soon_threadsafe(
                        lambda: setattr(self.progress, "value", self.progress.value + 1)
                    )

                if settings.translate_clozemaster and clozemaster_entries:
                    self.main_window.app.loop.call_soon_threadsafe(
                        lambda: self._append_log(
                            f"Translating {len(clozemaster_entries)} Clozemaster rows "
                            f"with {settings.translation_model}..."
                        )
                    )
                    translator = OpusMtTranslator(model_name=settings.translation_model)
                    clozemaster_entries = apply_translations_to_clozemaster_entries(
                        clozemaster_entries, translator
                    )
                    self.main_window.app.loop.call_soon_threadsafe(
                        lambda: self._append_log("Translation step finished")
                    )
            except Exception as exc:
                tb = traceback.format_exc()
                self.logger.error("Rank stage failed: %s\n%s", exc, tb)
                self.main_window.app.loop.call_soon_threadsafe(
                    lambda e=exc: self.main_window.error_dialog("Rank failed", str(e))
                )
                self.main_window.app.loop.call_soon_threadsafe(self._finish_run)
                return

            def done() -> None:
                self._debug("rank done callback", canceled=self.cancel_requested)
                if self.cancel_requested:
                    self._append_log("Rank stage canceled")
                    self._finish_run(reset_rank_state=True)
                    return
                for name, rows in results.items():
                    html = render_html(name, rows)
                    out_path = out_dir / f"{Path(name).stem}.html"
                    out_path.write_text(html, encoding="utf-8")
                    self._append_log(f"Wrote: {out_path}")
                added, skipped = append_unique_clozemaster_entries(
                    Path("clozemaster_input_realpolish.tsv"), clozemaster_entries
                )
                self._append_log(
                    "Clozemaster CSV updated: "
                    f"added={added}, skipped_duplicates={skipped}"
                )
                self.main_window.info_dialog("Done", f"Saved HTML to {out_dir}")
                self._append_log("Rank stage finished")
                self._finish_run(reset_rank_state=True)

            self.main_window.app.loop.call_soon_threadsafe(done)

        threading.Thread(target=run, daemon=True).start()

    def cancel(self, _widget) -> None:
        self._debug("cancel pressed", is_running=self.is_running)
        if self.is_running:
            self.cancel_requested = True
            self._append_log("Cancel requested")
            return
        self.staged_results.clear()
        self.staged_sentences.clear()
        self._preview_terms_cache.clear()
        if self.cancel_btn in self.tokenize_button_row.children:
            self.tokenize_button_row.remove(self.cancel_btn)
        self._clear_zipf_examples()
        self._set_listing_controls_ready(False)
        self._refresh_preview()
        self._append_log("Staged tokenization cleared")

    def _finish_run(self, reset_rank_state: bool = False) -> None:
        self._debug(
            "finish run",
            reset_rank_state=reset_rank_state,
            staged_files=len(self.staged_results),
        )
        self.is_running = False
        self.cancel_requested = False
        self.tokenize_btn.enabled = True
        self.clear_files_btn.enabled = True
        if reset_rank_state:
            self.staged_results.clear()
            self.staged_sentences.clear()
            self._preview_terms_cache.clear()
            if self.cancel_btn in self.tokenize_button_row.children:
                self.tokenize_button_row.remove(self.cancel_btn)
            self._clear_zipf_examples()
            self._set_listing_controls_ready(False)
            self._refresh_preview()
        elif self.staged_results:
            self._set_listing_controls_ready(True)
            self.export_btn.enabled = True
        else:
            self._set_listing_controls_ready(False)
