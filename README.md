# Polish Vocabulary Extractor

Desktop + CLI tool for extracting and ranking Polish vocabulary from HTML/text sources.

It tokenizes and lemmatizes with UDPipe, ranks words against general corpus frequency, exports per-file HTML lists, and appends deduplicated Clozemaster rows.

## Core Features
- HTML cleaning with configurable start/end markers.
- UDPipe tokenization + lemma grouping.
- Ranking with blended absolute/relative scoring (`wordfreq`-based).
- Zipf min/max filtering.
- Two-stage GUI flow: `Tokenize` then `Create Lists + Export`.
- Optional ignore patterns (wildcards), persisted between sessions.
- Clozemaster export to `clozemaster_input_realpolish.tsv`.
- Optional Polish->English sentence translation for Clozemaster export (OPUS-MT).

## Quick Start
1. Install dependencies.
2. Ensure UDPipe model file exists in `data/udpipe/`.
3. (Optional) Pre-cache OPUS Polish->English model for translation.
4. Run `python app_toga.py`.
5. Tokenize first, then export.

## Install

### Core dependencies
```bash
pip install beautifulsoup4 ufal.udpipe wordfreq rich toga
```

### Optional translation dependencies
```bash
pip install transformers sentencepiece torch
```

### Optional YouTube captions dependency
Install `yt-dlp` if you want to tokenize from YouTube caption links:
```bash
pip install yt-dlp
```

## Prepare Models

### 1) UDPipe model (required)
The app expects:
- `data/udpipe/polish-pdb-ud-2.5-191206.udpipe`

### 2) OPUS Polish->English model (optional, recommended to prewarm)
If you enable translation in the GUI, pre-download the model once to avoid first-run stall:

```bash
python - <<'PY'
from transformers import MarianMTModel, MarianTokenizer
name = "Helsinki-NLP/opus-mt-pl-en"
MarianTokenizer.from_pretrained(name)
MarianMTModel.from_pretrained(name)
print("Cached:", name)
PY
```

Default cache path (if not overridden):
- `~/.cache/huggingface/hub/models--Helsinki-NLP--opus-mt-pl-en`

## Run

### GUI
```bash
python app_toga.py
```

### CLI
```bash
python polish_vocab.py data/your_file.html
```

## GUI Workflow

### 1) Tokenization
- Add files (drag/drop or Browse).
- Optional: click `YouTube links…` and paste one URL per line.
- Set start/end markers.
- Optional: enable `Ignore words` and enter wildcard patterns (one per line).
- Click `Tokenize`.

### 2) Listing + Export
- Controls are enabled only after tokenization.
- Set:
  - `Include words with frequency 1`
  - `Include inflections in list`
  - Zipf min/max sliders
  - `Balance (absolute vs relative)` slider
  - `Max number of phrases per document`
  - Optional `Translate Clozemaster sentences (OPUS)`
- Click `Create Lists + Export`.

## Output
- HTML list per source file in `output_html/`.
- Appended deduplicated Clozemaster rows in `clozemaster_input_realpolish.tsv`.
- Clozemaster sentence rows longer than 300 chars are discarded.

## Notes
- Ignore patterns support wildcards (`*`, `?`) and are persisted in `.cache/app_toga_state.json`.
- First-time translation can be slow if the OPUS model is not already cached.
- Translation is optional; if disabled, Clozemaster English field stays empty.

## Tests
```bash
pytest -q
```
