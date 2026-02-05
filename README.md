# 🇵🇱 Polish Vocabulary Extractor

This is a personal NLP tool that helps language learners extract and prioritize vocabulary from any Polish text (e.g. articles, stories, blog posts). It identifies the **most "unusually" frequent** words by comparing the input text to general Polish usage.

---

## ✨ Features

* Cleans HTML and input noise using `BeautifulSoup`
* Trims HTML to a configurable start/end range from `config.json`
* Tokenizes and lemmatizes Polish words using `spaCy` and **Morfeusz2**
* Clusters conjugated forms to their root lemma
* Compares word frequencies to general Polish usage with `wordfreq`
* Uses TF-IDF-like logic to surface the most *notably frequent* words
* Outputs a sorted list of lemmas for vocabulary study

---

## 📦 Dependencies

Install via `pip`:

```bash
pip install beautifulsoup4 spacy wordfreq scikit-learn morfeusz2
python -m spacy download pl_core_news_sm
```

💡 **Note:** `morfeusz2` may require extra system libraries depending on your OS. Refer to its [GitHub](https://github.com/WojciechMula/morfeusz2) or use `conda` if pip fails.

---

## 📁 Folder Structure

```
polish_vocab_extractor/
│
├── config.json                  # Start/end markers for main content
├── data/
│   └── sample_input.html         # Polish text file or pasted HTML
│
├── output/
│   └── vocab_list.csv            # Lemma, frequency, relative score
│
├── polish_vocab.py              # Main execution script
├── extractor/
│   ├── __init__.py
│   ├── cleaner.py               # HTML/text cleaning
│   ├── tokenizer.py             # spaCy + Morfeusz2 lemmatizer
│   ├── frequency.py             # wordfreq + TF-IDF scoring
│   └── utils.py                 # Shared helpers
│
└── README.md
```

---

## 🚀 How It Works

1. **Input**: You provide a block of Polish text or HTML content.
2. **Preprocessing**: `config.json` defines the start/end markers for main content, then `BeautifulSoup` strips tags and formatting.
3. **Tokenization**: `spaCy` splits text; `Morfeusz2` finds correct lemmas.
4. **Frequency Comparison**:

   * `wordfreq` estimates global word frequency
   * Words are scored by their *local vs. global* frequency difference (Zipf scale)
5. **Output**: You get a ranked `.csv` of words worth learning first.

---

## ⚠️ Known Limitations

* Some proper nouns or idioms may not be well-handled by `Morfeusz2`
* Frequency comparison relies on generic corpora (context-insensitive)
* Definitions and translations are not provided (yet)
* No GUI or web interface – CLI-only for now

---

## 🛠️ Future Features

* Gloss lookups from Wiktionary
* Flashcard deck export (.csv or Anki format)
* Web app or notebook interface
* Interactive CLI (e.g. `typer`-based)
* Filtering by part-of-speech (e.g. only nouns or verbs)

---

## 👤 Author

This tool was built as a personal project to aid Polish language acquisition. Contributions or ideas welcome!

---

Let me know if you'd like this saved as a file, or if you want to move forward with implementing the `tokenizer.py` module using `spaCy` + `Morfeusz2`.
## 🧰 CLI Options

* Default: uses `wordfreq` scoring (local vs. global frequency).
* `--plain`: show the raw top list without `wordfreq` scoring.
* `--allow-ones`: include words that appear only once (default excludes them).
* `--allow-inflections-in-list`: include inflected forms in the top list (default shows only lemmas).
