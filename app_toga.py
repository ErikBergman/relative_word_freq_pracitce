from __future__ import annotations

import logging
import sys
import traceback
import threading
import time
from collections import Counter
import math
import json
from pathlib import Path
from typing import Iterable

import toga
from toga.constants import Direction
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from app_logic import (
    Settings,
    apply_ignore_patterns,
    build_rows,
    render_html,
)
from extractor.frequency import blend_scores_from_terms, precompute_score_terms
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
    ZIPF_MIN = 0.0
    ZIPF_MAX = 7.0
    STATE_PATH = Path(".cache/app_toga_state.json")

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
        self._debug_seq = 0
        self._preview_refresh_active = False
        self._preview_terms_cache: dict[str, object] = {}

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
        self.balance_slider = toga.Slider(value=0.5, min=0.0, max=1.0, style=Pack(flex=1))
        self.balance_slider.on_change = self._on_balance_change
        self.balance_label = toga.Label("a = 0.50")

        self.allow_ones = toga.Switch("Include words with frequency 1")
        self.allow_inflections = toga.Switch("Include inflections in list")
        self.use_wordfreq = toga.Switch("Use wordfreq scoring", value=True)
        self.enable_ignore_words = toga.Switch(
            "Ignore words", on_change=self._toggle_ignore_words
        )
        self.ignore_words_input = toga.MultilineTextInput(
            placeholder="One pattern per line, wildcards allowed (e.g. *ing, rp*)",
            on_change=self._on_ignore_words_change,
            style=Pack(height=120),
        )
        self.ignore_words_box = toga.Box(style=Pack(direction=COLUMN, margin_top=8))
        self.ignore_words_box.add(
            toga.Label("Ignore patterns (one per row, supports * and ?)")
        )
        self.ignore_words_box.add(self.ignore_words_input)

        self.zipf_min_slider = toga.Slider(
            value=1.0, min=self.ZIPF_MIN, max=self.ZIPF_MAX, style=Pack(flex=1)
        )
        self.zipf_min_slider.on_change = self._on_zipf_min_change
        self.zipf_max_slider = toga.Slider(
            value=7.0, min=self.ZIPF_MIN, max=self.ZIPF_MAX, style=Pack(flex=1)
        )
        self.zipf_max_slider.on_change = self._on_zipf_max_change
        self.zipf_value_label = toga.Label("Zipf exclusion range (Tokenize to use)")
        self.zipf_min_label = toga.Label("Exclude below (min): 1.0")
        self.zipf_max_label = toga.Label("Exclude above (max): 7.0")
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
        self.zipf_box.add(self.zipf_min_label)
        self.zipf_box.add(self.zipf_min_slider)
        self.zipf_box.add(self.zipf_max_label)
        self.zipf_box.add(self.zipf_max_slider)
        self.zipf_box.add(self.zipf_scale_row)
        self.zipf_box.add(self.zipf_example_row)
        self._set_zipf_controls_ready(False)

        self.progress = toga.ProgressBar(max=1, value=0, style=Pack(flex=1))
        self.log_box = toga.MultilineTextInput(
            readonly=True, style=Pack(flex=1, height=130, margin_top=8)
        )
        self.start_btn = toga.Button(
            "Tokenize", on_press=self.start, style=Pack(margin_top=10)
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
        options_box.add(self.enable_ignore_words)
        options_box.add(toga.Label("Balance (absolute vs relative)", style=Pack(margin_top=8)))
        options_box.add(self.balance_label)
        options_box.add(self.balance_slider)
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
        main_box.add(self.zipf_box)
        main_box.add(self.progress)
        self.button_row = toga.Box(style=Pack(direction=ROW))
        self.button_row.add(self.start_btn)
        main_box.add(self.button_row)
        main_box.add(toga.Label("Log", style=Pack(margin_top=8)))
        main_box.add(self.log_box)

        self.preview_box = toga.Box(style=Pack(direction=COLUMN, margin=12))
        self.preview_box.add(toga.Label("Top List Preview"))
        self.preview_text = toga.MultilineTextInput(
            readonly=True,
            value="Preview updates after tokenization.",
            style=Pack(flex=1),
        )
        self.preview_box.add(self.preview_text)

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_box = main_box
        self.root_scroll = toga.ScrollContainer(
            content=main_box,
            horizontal=False,
            vertical=True,
            style=Pack(flex=1),
        )
        self.split = toga.SplitContainer(
            direction=Direction.VERTICAL,
            content=[(self.root_scroll, 0.60), (self.preview_box, 0.40)],
            style=Pack(flex=1),
        )
        self.main_window.content = self.split
        self.main_window.size = (1400, 900)
        self.main_window.show()
        self._set_macos_app_identity()

        # Best-effort drag-and-drop support.
        # Best-effort drag-and-drop support (platform dependent).
        try:
            self.main_window.on_drop = self.on_drop
        except Exception:
            pass
        self._load_persistent_state()
        self._append_log("GUI initialized")
        self._debug("startup complete", ignore_enabled=self.enable_ignore_words.value)

    def _debug(self, message: str, **fields) -> None:
        self._debug_seq += 1
        payload = " ".join(f"{key}={value}" for key, value in fields.items())
        thread_name = threading.current_thread().name
        line = f"[DBG {self._debug_seq:05d}] {message} thread={thread_name}"
        if payload:
            line = f"{line} {payload}"
        self.logger.info(line)

    def _set_macos_app_identity(self) -> None:
        if sys.platform != "darwin":
            return
        try:
            from rubicon.objc import ObjCClass

            process_info = ObjCClass("NSProcessInfo").processInfo
            process_info.setProcessName_(self.formal_name)

            ns_app = ObjCClass("NSApplication").sharedApplication
            ns_image = ObjCClass("NSImage").alloc().initWithContentsOfFile_(
                str(Path("data/book_icon2.png").resolve())
            )
            if ns_image is not None:
                ns_app.setApplicationIconImage_(ns_image)
        except Exception:
            # Non-fatal: this is a best-effort tweak for script mode on macOS.
            pass

    def _set_zipf_controls_ready(self, ready: bool) -> None:
        self.zipf_min_slider.enabled = ready
        self.zipf_max_slider.enabled = ready
        if ready:
            self.zipf_value_label.text = "Zipf exclusion range"
        else:
            self.zipf_value_label.text = "Zipf exclusion range (Tokenize to use)"

    def _toggle_ignore_words(self, _widget) -> None:
        self._debug("toggle ignore words", enabled=self.enable_ignore_words.value)
        if self.enable_ignore_words.value:
            if self.ignore_words_box not in self.main_box.children:
                self.main_box.add(self.ignore_words_box)
                self._append_log("Ignore words box shown")
        else:
            if self.ignore_words_box in self.main_box.children:
                self.main_box.remove(self.ignore_words_box)
                self._append_log("Ignore words box hidden")
        self._save_persistent_state()

    def _on_ignore_words_change(self, _widget) -> None:
        self._debug("ignore words changed", length=len(self.ignore_words_input.value or ""))
        self._save_persistent_state()

    def _save_persistent_state(self) -> None:
        state = {
            "ignore_words_enabled": bool(self.enable_ignore_words.value),
            "ignore_words_text": self.ignore_words_input.value or "",
        }
        self.STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_persistent_state(self) -> None:
        if not self.STATE_PATH.exists():
            return
        try:
            state = json.loads(self.STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        self.ignore_words_input.value = str(state.get("ignore_words_text", ""))
        enabled = bool(state.get("ignore_words_enabled", False))
        self.enable_ignore_words.value = enabled
        if enabled and self.ignore_words_box not in self.main_box.children:
            self.main_box.add(self.ignore_words_box)

    @staticmethod
    def _quantize_slider(value: float) -> float:
        return round(float(value) * 10.0) / 10.0

    def _sync_zipf_labels(self) -> None:
        self.zipf_min_label.text = (
            f"Exclude below (min): {float(self.zipf_min_slider.value):.1f}"
        )
        self.zipf_max_label.text = (
            f"Exclude above (max): {float(self.zipf_max_slider.value):.1f}"
        )

    def _on_zipf_min_change(self, _widget) -> None:
        self._debug("zipf min change", raw=self.zipf_min_slider.value)
        snapped = self._quantize_slider(float(self.zipf_min_slider.value))
        if abs(float(self.zipf_min_slider.value) - snapped) > 1e-9:
            self.zipf_min_slider.value = snapped
            return
        if snapped > float(self.zipf_max_slider.value):
            self.zipf_max_slider.value = snapped
        self._sync_zipf_labels()
        self._refresh_preview()

    def _on_zipf_max_change(self, _widget) -> None:
        self._debug("zipf max change", raw=self.zipf_max_slider.value)
        snapped = self._quantize_slider(float(self.zipf_max_slider.value))
        if abs(float(self.zipf_max_slider.value) - snapped) > 1e-9:
            self.zipf_max_slider.value = snapped
            return
        if snapped < float(self.zipf_min_slider.value):
            self.zipf_min_slider.value = snapped
        self._sync_zipf_labels()
        self._refresh_preview()

    def _on_balance_change(self, _widget) -> None:
        snapped = round(float(self.balance_slider.value) * 100.0) / 100.0
        if abs(float(self.balance_slider.value) - snapped) > 1e-9:
            self.balance_slider.value = snapped
            return
        self.balance_label.text = f"a = {snapped:.2f}"
        self._refresh_preview()

    def _clear_zipf_examples(self) -> None:
        for label in self.zipf_example_labels:
            label.text = "—"

    @staticmethod
    def _clip_bucket_word(word: str, max_chars: int = 11) -> str:
        # Keep bucket columns readable by hiding endings for long words.
        return word if len(word) <= max_chars else word[:max_chars]

    def _update_zipf_examples(self) -> None:
        t0 = time.perf_counter()
        self._debug("zipf examples start", staged_files=len(self.staged_results))
        self._clear_zipf_examples()
        if not self.staged_results:
            self._debug("zipf examples skip", reason="no_staged_results")
            return
        try:
            from wordfreq import zipf_frequency
        except Exception:
            self._append_log("wordfreq not available, Zipf examples skipped")
            self._debug("zipf examples skip", reason="wordfreq_missing")
            return

        merged_lemma_counts: Counter = Counter()
        for _counts, groups in self.staged_results.values():
            for lemma, forms in groups.items():
                merged_lemma_counts[lemma] += sum(forms.values())

        buckets: dict[int, list[str]] = {i: [] for i in range(8)}
        for lemma, _count in merged_lemma_counts.most_common():
            zipf = zipf_frequency(lemma, "pl")
            level = int(math.floor(zipf))
            if level < 0 or level > 7:
                continue
            if len(buckets[level]) < 3 and lemma not in buckets[level]:
                buckets[level].append(lemma)

        for i in range(8):
            clipped = [self._clip_bucket_word(word) for word in buckets[i][:3]]
            self.zipf_example_labels[i].text = "\n\n".join(clipped) if clipped else "—"
        self._debug(
            "zipf examples done",
            seconds=f"{time.perf_counter() - t0:.3f}",
            unique_lemmas=len(merged_lemma_counts),
        )

    def _current_settings(self, limit_value: int | None = None) -> Settings:
        if limit_value is None:
            try:
                limit_value = int(self.limit_input.value or 50)
            except ValueError:
                limit_value = 50
        return Settings(
            start=self.start_input.value,
            end=self.end_input.value,
            limit=limit_value,
            allow_ones=self.allow_ones.value,
            allow_inflections=self.allow_inflections.value,
            use_wordfreq=self.use_wordfreq.value,
            min_zipf=float(self.zipf_min_slider.value),
            max_zipf=float(self.zipf_max_slider.value),
            balance_a=float(self.balance_slider.value),
            ignore_patterns=(
                tuple(
                    line.strip().lower()
                    for line in (self.ignore_words_input.value or "").splitlines()
                    if line.strip()
                )
                if self.enable_ignore_words.value
                else ()
            ),
        )

    def _rebuild_preview_cache(self) -> None:
        merged_counts: Counter = Counter()
        merged_groups: dict[str, dict[str, int]] = {}
        for counts, groups in self.staged_results.values():
            merged_counts.update(counts)
            for lemma, forms in groups.items():
                dst = merged_groups.setdefault(lemma, {})
                for form, cnt in forms.items():
                    dst[form] = dst.get(form, 0) + cnt

        lemma_counts = Counter({lemma: sum(forms.values()) for lemma, forms in merged_groups.items()})
        self._preview_terms_cache = {
            "merged_counts": merged_counts,
            "merged_groups": merged_groups,
            "lemma_counts": lemma_counts,
            "token_terms": precompute_score_terms(merged_counts),
            "lemma_terms": precompute_score_terms(lemma_counts),
        }
        self._debug(
            "preview cache rebuilt",
            token_types=len(merged_counts),
            lemmas=len(lemma_counts),
        )

    def _refresh_preview(self) -> None:
        if self._preview_refresh_active:
            self._debug("preview refresh skipped", reason="already_active")
            return
        self._preview_refresh_active = True
        t0 = time.perf_counter()
        self._debug("preview refresh start", staged_files=len(self.staged_results))
        if not self.staged_results:
            self.preview_text.value = "Preview updates after tokenization."
            self._debug(
                "preview refresh done",
                seconds=f"{time.perf_counter() - t0:.3f}",
                reason="no_staged_results",
            )
            self._preview_refresh_active = False
            return

        try:
            settings = self._current_settings()
            self._debug(
                "preview settings",
                limit=settings.limit,
                use_wordfreq=settings.use_wordfreq,
                min_zipf=f"{settings.min_zipf:.1f}",
                max_zipf=f"{settings.max_zipf:.1f}",
                balance_a=f"{settings.balance_a:.2f}",
                ignore_patterns=len(settings.ignore_patterns),
            )
            if not self._preview_terms_cache:
                self._rebuild_preview_cache()

            merged_counts = self._preview_terms_cache["merged_counts"]
            merged_groups = self._preview_terms_cache["merged_groups"]
            lemma_counts = self._preview_terms_cache["lemma_counts"]

            if settings.use_wordfreq:
                terms_key = "token_terms" if settings.allow_inflections else "lemma_terms"
                terms = self._preview_terms_cache[terms_key]
                if not settings.allow_ones:
                    source_counts = merged_counts if settings.allow_inflections else lemma_counts
                    terms = {
                        word: term for word, term in terms.items() if source_counts.get(word, 0) > 1
                    }
                scored = blend_scores_from_terms(
                    terms,
                    limit=settings.limit,
                    balance_a=settings.balance_a,
                    min_global_zipf=settings.min_zipf,
                    max_global_zipf=settings.max_zipf,
                )
                preview_rows = scored[: min(25, len(scored))]
                rows_len = len(scored)
            else:
                rows = build_rows(merged_counts, merged_groups, settings)
                preview_rows = rows[: min(25, len(rows))]
                rows_len = len(rows)
            self._debug(
                "preview rows ready",
                all_rows=rows_len,
                preview_rows=len(preview_rows),
            )
            if not preview_rows:
                self.preview_text.value = "No words match current filters."
                self._debug(
                    "preview refresh done",
                    seconds=f"{time.perf_counter() - t0:.3f}",
                    reason="empty_after_filter",
                )
                return

            lines = [f"{'Word':24} {'Count':>7} {'Score':>8}"]
            if settings.use_wordfreq:
                for word, count, score in preview_rows:
                    lines.append(f"{word[:24]:24} {count:7d} {score:>8.3f}")
            else:
                for row in preview_rows:
                    score = "" if row.score is None else f"{row.score:.3f}"
                    word = row.word[:24]
                    lines.append(f"{word:24} {row.count:7d} {score:>8}")
            self.preview_text.value = "\n".join(lines)
            self._debug(
                "preview refresh done",
                seconds=f"{time.perf_counter() - t0:.3f}",
                lines=len(lines),
            )
        except Exception as exc:
            tb = traceback.format_exc()
            self.logger.error("Preview refresh failed: %s\n%s", exc, tb)
            self._append_log(f"Preview error: {exc}")
            self.preview_text.value = f"Preview error: {exc}"
            self._debug("preview refresh error", error=repr(exc))
        finally:
            self._preview_refresh_active = False

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
        self._debug("start pressed", is_running=self.is_running, files=len(self.files))
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

        settings = self._current_settings()
        out_dir = Path("output_html")
        out_dir.mkdir(exist_ok=True)
        self._append_log(
            f"Start run: files={len(self.files)} limit={limit_value} "
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
        self.start_btn.enabled = False
        self._debug(
            "run dispatch",
            mode=("rank" if self.start_btn.text == "Rank" else "tokenize"),
        )

        if self.start_btn.text == "Rank":
            self._run_rank_stage(settings, out_dir)
        else:
            self._run_tokenize_stage(settings)

    def _run_tokenize_stage(self, settings: Settings) -> None:
        self.staged_results.clear()
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
                    tokens = tokenize(text, progress=lambda t, a: report("tokenize", t, a))
                    self._debug(
                        "tokenize tokens ready", file=path.name, token_count=len(tokens)
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
                    self._finish_run()
                    return
                self._append_log("Tokenize stage finished")
                self._rebuild_preview_cache()
                self._update_zipf_examples()
                self._refresh_preview()
                self._set_zipf_controls_ready(True)
                self.start_btn.text = "Rank"
                if self.cancel_btn not in self.button_row.children:
                    self.button_row.add(self.cancel_btn)
                self._finish_run()

            self.main_window.app.loop.call_soon_threadsafe(done)

        threading.Thread(target=run, daemon=True).start()

    def _run_rank_stage(self, settings: Settings, out_dir: Path) -> None:
        self._append_log("Rank stage started")
        self._debug("rank stage init", staged_files=len(self.staged_results))

        def run() -> None:
            self._debug("rank stage thread start", staged_files=len(self.staged_results))
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
                    self._debug("rank rows built", file=name, rows=len(rows))
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
        self._preview_terms_cache.clear()
        self.start_btn.text = "Tokenize"
        if self.cancel_btn in self.button_row.children:
            self.button_row.remove(self.cancel_btn)
        self._clear_zipf_examples()
        self._set_zipf_controls_ready(False)
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
        self.start_btn.enabled = True
        if reset_rank_state:
            self.staged_results.clear()
            self._preview_terms_cache.clear()
            self.start_btn.text = "Tokenize"
            if self.cancel_btn in self.button_row.children:
                self.button_row.remove(self.cancel_btn)
            self._clear_zipf_examples()
            self._set_zipf_controls_ready(False)
            self._refresh_preview()
        elif self.staged_results:
            self._set_zipf_controls_ready(True)
        else:
            self._set_zipf_controls_ready(False)


def main() -> None:
    PolishVocabApp(
        "Polish Vocabulary Extractor",
        "org.example.polishvocab",
        app_name="PolishVocabularyExtractor",
        icon=Path("data/book_icon2.png"),
    ).main_loop()


if __name__ == "__main__":
    main()
