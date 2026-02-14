from __future__ import annotations

import logging
import traceback
import threading
from collections import Counter
import math
from pathlib import Path
from typing import Iterable

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from app_logic import Settings, build_rows, process_file, render_html
from extractor.cleaner import extract_text
from extractor.tokenizer import lemma_groups, tokenize


def _iter_paths_from_drop(*args) -> Iterable[Path]:
    if not args:
        return []
    # Toga may pass (widget, path, x, y) or (widget, paths)
    for item in args:
        if isinstance(item, (list, tuple)):
            return [Path(p) for p in item]
        if isinstance(item, str):
            return [Path(item)]
    return []


def _coerce_path(value) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        return Path(value)
    # Toga may return path-like dialog objects.
    maybe_path = getattr(value, "path", None)
    if isinstance(maybe_path, str):
        return Path(maybe_path)
    try:
        return Path(str(value))
    except Exception:
        return None


class PolishVocabApp(toga.App):
    def startup(self) -> None:
        self.files: list[Path] = []
        self.staged_results: dict[str, tuple[Counter, dict[str, dict[str, int]]]] = {}
        self.is_running = False
        self.cancel_requested = False
        self.step_totals = {"clean": 1, "tokenize": 0, "lemmatize": 0, "count": 1}
        self.logger = logging.getLogger("app_toga")
        self.logger.setLevel(logging.INFO)
        self.logger.handlers.clear()
        out_dir = Path("output_html")
        out_dir.mkdir(exist_ok=True)
        file_handler = logging.FileHandler(out_dir / "app_toga.log", encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        self.logger.addHandler(file_handler)

        self.file_list = toga.MultilineTextInput(
            readonly=True,
            placeholder="Drag files here or use Browse…",
            style=Pack(flex=1, height=120),
        )
        browse_btn = toga.Button("Browse…", on_press=self.browse, style=Pack(margin_top=5))

        self.start_input = toga.TextInput(
            value="Download mp3 file:", style=Pack(flex=1)
        )
        self.end_input = toga.TextInput(value="<hr />", style=Pack(flex=1))

        self.limit_input = toga.TextInput(value="50", style=Pack(width=120))

        self.allow_ones = toga.Switch("Include words with frequency 1")
        self.allow_inflections = toga.Switch("Include inflections in list")
        self.use_wordfreq = toga.Switch("Use wordfreq scoring", value=True)
        self.enable_zipf_filter = toga.Switch(
            "Enable Zipf filter slider", on_change=self._toggle_zipf_slider
        )

        self.zipf_slider = toga.Slider(value=1.0, min=0.0, max=7.0, style=Pack(flex=1))
        self.zipf_slider.on_change = self._on_zipf_slider_change
        self.zipf_value_label = toga.Label("Minimum global Zipf: 1.0")
        self.zipf_scale_row = toga.Box(style=Pack(direction=ROW, margin_top=4))
        self.zipf_example_row = toga.Box(style=Pack(direction=ROW, margin_top=2))
        self.zipf_example_labels: list[toga.Label] = []
        for i in range(8):
            self.zipf_scale_row.add(toga.Label(str(i), style=Pack(flex=1, font_size=10)))
            label = toga.Label("—", style=Pack(flex=1, font_size=9))
            self.zipf_example_labels.append(label)
            self.zipf_example_row.add(label)
        self.zipf_box = toga.Box(style=Pack(direction=COLUMN, margin_top=8))
        self.zipf_box.add(self.zipf_value_label)
        self.zipf_box.add(self.zipf_slider)
        self.zipf_box.add(self.zipf_scale_row)
        self.zipf_box.add(self.zipf_example_row)

        self.progress = toga.ProgressBar(max=1, value=0, style=Pack(flex=1))
        self.log_box = toga.MultilineTextInput(
            readonly=True, style=Pack(flex=1, height=130, margin_top=8)
        )
        self.start_btn = toga.Button(
            "Tokenize and rank", on_press=self.start, style=Pack(margin_top=10)
        )
        self.cancel_btn = toga.Button(
            "Cancel", on_press=self.cancel, style=Pack(margin_top=10, margin_left=8)
        )

        rules_box = toga.Box(style=Pack(direction=COLUMN, flex=1, margin_right=10))
        rules_box.add(toga.Label("Start marker"))
        rules_box.add(self.start_input)
        rules_box.add(toga.Label("End marker", style=Pack(margin_top=8)))
        rules_box.add(self.end_input)

        options_box = toga.Box(style=Pack(direction=COLUMN, flex=1))
        options_box.add(toga.Label("Options"))
        options_box.add(self.allow_ones)
        options_box.add(self.allow_inflections)
        options_box.add(self.use_wordfreq)
        options_box.add(self.enable_zipf_filter)
        options_box.add(toga.Label("Limit", style=Pack(margin_top=8)))
        options_box.add(self.limit_input)

        top_row = toga.Box(style=Pack(direction=ROW, margin_top=10))
        top_row.add(rules_box)
        top_row.add(options_box)

        main_box = toga.Box(style=Pack(direction=COLUMN, margin=12))
        main_box.add(toga.Label("Files"))
        main_box.add(self.file_list)
        main_box.add(browse_btn)
        main_box.add(top_row)
        main_box.add(self.progress)
        self.button_row = toga.Box(style=Pack(direction=ROW))
        self.button_row.add(self.start_btn)
        main_box.add(self.button_row)
        main_box.add(toga.Label("Log", style=Pack(margin_top=8)))
        main_box.add(self.log_box)

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_box = main_box
        self.main_window.content = main_box
        self.main_window.show()

        # Best-effort drag-and-drop support.
        # Best-effort drag-and-drop support (platform dependent).
        try:
            self.main_window.on_drop = self.on_drop
        except Exception:
            pass
        self._append_log("GUI initialized")

    def _toggle_zipf_slider(self, _widget) -> None:
        if self.enable_zipf_filter.value:
            if self.zipf_box not in self.main_box.children:
                self.main_box.add(self.zipf_box)
                self._append_log("Zipf slider shown")
            self.start_btn.text = "Tokenize"
        else:
            if self.zipf_box in self.main_box.children:
                self.main_box.remove(self.zipf_box)
                self._append_log("Zipf slider hidden")
            self.start_btn.text = "Tokenize and rank"
            if self.cancel_btn in self.button_row.children:
                self.button_row.remove(self.cancel_btn)
            self.staged_results.clear()
            self._clear_zipf_examples()

    def _on_zipf_slider_change(self, _widget) -> None:
        quantized = round(float(self.zipf_slider.value) * 10.0) / 10.0
        if abs(float(self.zipf_slider.value) - quantized) > 1e-9:
            self.zipf_slider.value = quantized
            return
        self.zipf_value_label.text = f"Minimum global Zipf: {quantized:.1f}"

    def _clear_zipf_examples(self) -> None:
        for label in self.zipf_example_labels:
            label.text = "—"

    @staticmethod
    def _clip_bucket_word(word: str, max_chars: int = 11) -> str:
        # Keep bucket columns readable by hiding endings for long words.
        return word if len(word) <= max_chars else word[:max_chars]

    def _update_zipf_examples(self) -> None:
        self._clear_zipf_examples()
        if not self.staged_results:
            return
        try:
            from wordfreq import zipf_frequency
        except Exception:
            self._append_log("wordfreq not available, Zipf examples skipped")
            return

        merged_counts: Counter = Counter()
        for counts, _groups in self.staged_results.values():
            merged_counts.update(counts)

        buckets: dict[int, list[str]] = {i: [] for i in range(8)}
        for word, _count in merged_counts.most_common():
            zipf = zipf_frequency(word, "pl")
            level = int(math.floor(zipf))
            if level < 0 or level > 7:
                continue
            if len(buckets[level]) < 3 and word not in buckets[level]:
                buckets[level].append(word)

        for i in range(8):
            clipped = [self._clip_bucket_word(word) for word in buckets[i][:3]]
            self.zipf_example_labels[i].text = "\n\n".join(clipped) if clipped else "—"

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
            path = _coerce_path(p)
            if path is not None:
                self._add_file(path)

    def on_drop(self, *args) -> None:
        for path in _iter_paths_from_drop(*args):
            if path.is_file():
                self._add_file(path)

    def _add_file(self, path: Path) -> None:
        if path in self.files:
            return
        self.files.append(path)
        self.file_list.value = "\n".join(str(p) for p in self.files)
        self._append_log(f"Added file: {path}")

    def _append_log(self, message: str) -> None:
        self.logger.info(message)
        existing = self.log_box.value or ""
        self.log_box.value = (existing + ("\n" if existing else "") + message)[-12000:]

    def start(self, _widget) -> None:
        if self.is_running:
            return
        if not self.files:
            self.main_window.error_dialog("No files", "Please add at least one file.")
            return

        try:
            limit_value = int(self.limit_input.value or 50)
        except ValueError:
            self.main_window.error_dialog("Invalid limit", "Limit must be a number.")
            return

        settings = Settings(
            start=self.start_input.value,
            end=self.end_input.value,
            limit=limit_value,
            allow_ones=self.allow_ones.value,
            allow_inflections=self.allow_inflections.value,
            use_wordfreq=self.use_wordfreq.value,
            min_zipf=(
                round(float(self.zipf_slider.value) * 10.0) / 10.0
                if self.enable_zipf_filter.value
                else 1.0
            ),
        )
        out_dir = Path("output_html")
        out_dir.mkdir(exist_ok=True)
        self._append_log(
            f"Start run: files={len(self.files)} limit={limit_value} "
            f"use_wordfreq={settings.use_wordfreq} allow_ones={settings.allow_ones} "
            f"allow_inflections={settings.allow_inflections} min_zipf={settings.min_zipf:.1f}"
        )

        self.progress.value = 0
        self.progress.max = 1
        self.step_totals = {"clean": 1, "tokenize": 0, "lemmatize": 0, "count": 1}
        self.cancel_requested = False
        self.is_running = True
        self.start_btn.enabled = False
        self.enable_zipf_filter.enabled = False

        if self.enable_zipf_filter.value and self.start_btn.text == "Rank":
            self._run_rank_stage(settings, out_dir)
        elif self.enable_zipf_filter.value:
            self._run_tokenize_stage(settings)
        else:
            self._run_full_stage(settings, out_dir)

    def _run_full_stage(self, settings: Settings, out_dir: Path) -> None:
        def run() -> None:
            results: dict[str, list] = {}

            def cb(step: str, total: int | None, advance: int) -> None:
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
                        lambda p=path: self._append_log(f"Processing file: {p.name}")
                    )
                    rows = process_file(path, settings, progress=cb)
                    results[path.name] = rows
                    self.main_window.app.loop.call_soon_threadsafe(
                        lambda n=path.name, c=len(rows): self._append_log(
                            f"Completed file: {n}, rows={c}"
                        )
                    )
            except Exception as exc:
                tb = traceback.format_exc()
                self.logger.error("Worker failed: %s\n%s", exc, tb)
                self.main_window.app.loop.call_soon_threadsafe(
                    lambda e=exc: self.main_window.error_dialog("Processing failed", str(e))
                )
                self.main_window.app.loop.call_soon_threadsafe(
                    lambda e=exc: self._append_log(f"ERROR: {e}")
                )
                return

            def done() -> None:
                if self.cancel_requested:
                    self._append_log("Run canceled")
                    self._finish_run()
                    return
                for name, rows in results.items():
                    html = render_html(name, rows)
                    out_path = out_dir / f"{Path(name).stem}.html"
                    out_path.write_text(html, encoding="utf-8")
                    self._append_log(f"Wrote: {out_path}")
                self.main_window.info_dialog("Done", f"Saved HTML to {out_dir}")
                self._append_log("Run finished")
                self._finish_run()

            self.main_window.app.loop.call_soon_threadsafe(done)

        threading.Thread(target=run, daemon=True).start()

    def _run_tokenize_stage(self, settings: Settings) -> None:
        self.staged_results.clear()
        self._append_log("Tokenize stage started")

        def run() -> None:
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
                    tokens = tokenize(text, progress=lambda t, a: report("tokenize", t, a))
                    groups = lemma_groups(
                        tokens,
                        text=text,
                        progress=lambda t, a: report("lemmatize", t, a),
                    )
                    counts = Counter(tokens)
                    if not settings.allow_ones:
                        counts = Counter({k: v for k, v in counts.items() if v > 1})
                    self.staged_results[path.name] = (counts, groups)
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
                if self.cancel_requested:
                    self._append_log("Tokenize stage canceled")
                    self.staged_results.clear()
                    self._finish_run()
                    return
                self._append_log("Tokenize stage finished")
                self._update_zipf_examples()
                self.start_btn.text = "Rank"
                if self.cancel_btn not in self.button_row.children:
                    self.button_row.add(self.cancel_btn)
                self._finish_run()

            self.main_window.app.loop.call_soon_threadsafe(done)

        threading.Thread(target=run, daemon=True).start()

    def _run_rank_stage(self, settings: Settings, out_dir: Path) -> None:
        self._append_log("Rank stage started")

        def run() -> None:
            results: dict[str, list] = {}
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
                    results[name] = rows
                    self.main_window.app.loop.call_soon_threadsafe(
                        lambda: setattr(self.progress, "value", self.progress.value + 1)
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
                if self.cancel_requested:
                    self._append_log("Rank stage canceled")
                    self._finish_run(reset_rank_state=True)
                    return
                for name, rows in results.items():
                    html = render_html(name, rows)
                    out_path = out_dir / f"{Path(name).stem}.html"
                    out_path.write_text(html, encoding="utf-8")
                    self._append_log(f"Wrote: {out_path}")
                self.main_window.info_dialog("Done", f"Saved HTML to {out_dir}")
                self._append_log("Rank stage finished")
                self._finish_run(reset_rank_state=True)

            self.main_window.app.loop.call_soon_threadsafe(done)

        threading.Thread(target=run, daemon=True).start()

    def cancel(self, _widget) -> None:
        if self.is_running:
            self.cancel_requested = True
            self._append_log("Cancel requested")
            return
        self.staged_results.clear()
        self.start_btn.text = "Tokenize"
        if self.cancel_btn in self.button_row.children:
            self.button_row.remove(self.cancel_btn)
        self._clear_zipf_examples()
        self._append_log("Staged tokenization cleared")

    def _finish_run(self, reset_rank_state: bool = False) -> None:
        self.is_running = False
        self.cancel_requested = False
        self.start_btn.enabled = True
        self.enable_zipf_filter.enabled = True
        if self.enable_zipf_filter.value:
            if reset_rank_state:
                self.staged_results.clear()
                self.start_btn.text = "Tokenize"
                if self.cancel_btn in self.button_row.children:
                    self.button_row.remove(self.cancel_btn)
                self._clear_zipf_examples()
        else:
            self.start_btn.text = "Tokenize and rank"


def main() -> None:
    PolishVocabApp("Polish Vocabulary Extractor", "org.example.polishvocab").main_loop()


if __name__ == "__main__":
    main()
