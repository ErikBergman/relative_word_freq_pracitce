from __future__ import annotations

import logging
import traceback
import threading
from pathlib import Path
from typing import Iterable

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from app_logic import Settings, process_file, render_html


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

        self.progress = toga.ProgressBar(max=1, value=0, style=Pack(flex=1))
        self.log_box = toga.MultilineTextInput(
            readonly=True, style=Pack(flex=1, height=130, margin_top=8)
        )
        start_btn = toga.Button("Start", on_press=self.start, style=Pack(margin_top=10))

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
        main_box.add(toga.Label("Log", style=Pack(margin_top=8)))
        main_box.add(self.log_box)
        main_box.add(start_btn)

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = main_box
        self.main_window.show()

        # Best-effort drag-and-drop support.
        # Best-effort drag-and-drop support (platform dependent).
        try:
            self.main_window.on_drop = self.on_drop
        except Exception:
            pass
        self._append_log("GUI initialized")

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
        )
        out_dir = Path("output_html")
        out_dir.mkdir(exist_ok=True)
        self._append_log(
            f"Start run: files={len(self.files)} limit={limit_value} "
            f"use_wordfreq={settings.use_wordfreq} allow_ones={settings.allow_ones} "
            f"allow_inflections={settings.allow_inflections}"
        )

        self.progress.value = 0
        self.progress.max = 1
        self.step_totals = {"clean": 1, "tokenize": 0, "lemmatize": 0, "count": 1}

        def run() -> None:
            results: dict[str, list] = {}

            def cb(step: str, total: int | None, advance: int) -> None:
                def update() -> None:
                    if total is not None:
                        self.step_totals[step] = total
                        self.progress.max = sum(self.step_totals.values())
                        self._append_log(f"Step '{step}' total set to {total}")
                    if advance:
                        self.progress.value = min(
                            self.progress.value + advance, self.progress.max
                        )
                        if step in {"clean", "count"}:
                            self._append_log(f"Step '{step}' advanced by {advance}")

                self.main_window.app.loop.call_soon_threadsafe(update)

            try:
                for path in self.files:
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
                    lambda: self.main_window.error_dialog("Processing failed", str(exc))
                )
                self.main_window.app.loop.call_soon_threadsafe(
                    lambda: self._append_log(f"ERROR: {exc}")
                )
                return

            def done() -> None:
                for name, rows in results.items():
                    html = render_html(name, rows)
                    out_path = out_dir / f"{Path(name).stem}.html"
                    out_path.write_text(html, encoding="utf-8")
                    self._append_log(f"Wrote: {out_path}")
                self.main_window.info_dialog("Done", f"Saved HTML to {out_dir}")
                self._append_log("Run finished")

            self.main_window.app.loop.call_soon_threadsafe(done)

        threading.Thread(target=run, daemon=True).start()


def main() -> None:
    PolishVocabApp("Polish Vocabulary Extractor", "org.example.polishvocab").main_loop()


if __name__ == "__main__":
    main()
