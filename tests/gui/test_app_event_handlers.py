from __future__ import annotations

from types import SimpleNamespace

from app_toga import PolishVocabApp


class _Box:
    def __init__(self, children: list[object] | None = None) -> None:
        self.children = list(children or [])

    def add(self, item: object) -> None:
        self.children.append(item)

    def remove(self, item: object) -> None:
        self.children.remove(item)


def _new_app() -> PolishVocabApp:
    app = object.__new__(PolishVocabApp)
    app._debug = lambda *args, **kwargs: None
    return app


def test_start_without_files_shows_error_dialog() -> None:
    app = _new_app()
    calls: list[tuple[str, str]] = []
    app.is_running = False
    app.files = []
    app._main_window = SimpleNamespace(
        error_dialog=lambda title, msg: calls.append((title, msg))
    )
    app.start(None)
    assert calls == [("No files", "Please add at least one file.")]


def test_toggle_ignore_words_adds_and_removes_box() -> None:
    app = _new_app()
    logs: list[str] = []
    app.main_box = _Box()
    app.ignore_words_box = object()
    app.enable_ignore_words = SimpleNamespace(value=True)
    app._save_persistent_state = lambda: None
    app._refresh_preview = lambda: None
    app._append_log = logs.append

    app._toggle_ignore_words(None)
    assert app.ignore_words_box in app.main_box.children
    assert "Ignore words box shown" in logs

    app.enable_ignore_words.value = False
    app._toggle_ignore_words(None)
    assert app.ignore_words_box not in app.main_box.children
    assert "Ignore words box hidden" in logs


def test_balance_slider_updates_label_and_triggers_refresh() -> None:
    app = _new_app()
    refreshed = {"count": 0}
    app.balance_slider = SimpleNamespace(value=0.5)
    app.balance_label = SimpleNamespace(text="")
    app._refresh_preview = lambda: refreshed.__setitem__("count", refreshed["count"] + 1)

    app._on_balance_change(None)
    assert app.balance_label.text == "a = 0.50"
    assert refreshed["count"] == 1


def test_zipf_min_change_snaps_and_updates_max() -> None:
    app = _new_app()
    refreshed = {"count": 0}
    app.zipf_min_slider = SimpleNamespace(value=2.0)
    app.zipf_max_slider = SimpleNamespace(value=1.0)
    app.zipf_min_label = SimpleNamespace(text="")
    app.zipf_max_label = SimpleNamespace(text="")
    app._refresh_preview = lambda: refreshed.__setitem__("count", refreshed["count"] + 1)

    app._on_zipf_min_change(None)

    assert app.zipf_max_slider.value == 2.0
    assert app.zipf_min_label.text == "Exclude below (min): 2.0"
    assert app.zipf_max_label.text == "Exclude above (max): 2.0"
    assert refreshed["count"] == 1


def test_cancel_idle_clears_state_and_resets_controls() -> None:
    app = _new_app()
    ready_calls: list[bool] = []
    logs: list[str] = []
    app.is_running = False
    app.staged_results = {"x": ({"a": 1}, {"a": {"a": 1}})}
    app.staged_sentences = {"x": ["Ala ma kota."]}
    app._preview_terms_cache = {"x": 1}
    app.tokenize_btn = SimpleNamespace(enabled=True)
    app.export_btn = SimpleNamespace(enabled=True)
    app.start_btn = app.tokenize_btn
    app.cancel_btn = object()
    app.tokenize_button_row = _Box([app.cancel_btn])
    app._clear_zipf_examples = lambda: None
    app._set_listing_controls_ready = lambda ready: ready_calls.append(ready)
    app._refresh_preview = lambda: None
    app._append_log = logs.append

    app.cancel(None)

    assert app.staged_results == {}
    assert app.staged_sentences == {}
    assert app._preview_terms_cache == {}
    assert app.cancel_btn not in app.tokenize_button_row.children
    assert ready_calls == [False]
    assert logs and logs[-1] == "Staged tokenization cleared"


def test_clear_files_clears_file_and_staged_state() -> None:
    app = _new_app()
    logs: list[str] = []
    ready_calls: list[bool] = []
    app.is_running = False
    app.files = ["a.html", "b.html"]
    app.file_list = SimpleNamespace(value="a.html\nb.html")
    app.staged_results = {"x": ({"a": 1}, {"a": {"a": 1}})}
    app.staged_sentences = {"x": ["Ala ma kota."]}
    app._preview_terms_cache = {"x": 1}
    app.export_btn = SimpleNamespace(enabled=True)
    app.cancel_btn = object()
    app.tokenize_button_row = _Box([app.cancel_btn])
    app._clear_zipf_examples = lambda: None
    app._set_listing_controls_ready = lambda ready: ready_calls.append(ready)
    app._refresh_preview = lambda: None
    app._append_log = logs.append

    app.clear_files(None)

    assert app.files == []
    assert app.file_list.value == ""
    assert app.staged_results == {}
    assert app.staged_sentences == {}
    assert app._preview_terms_cache == {}
    assert app.export_btn.enabled is False
    assert app.cancel_btn not in app.tokenize_button_row.children
    assert ready_calls == [False]
    assert logs and logs[-1] == "Cleared file list"
