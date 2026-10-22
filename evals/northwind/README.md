# Northwind Air test corpus

A made-up airline with 15 short policies. 25 conflicts and 25 near misses are planted on purpose, so the scanner can be scored. No real company's documents are used, so the corpus is safe to publish as a demo.

## Files

| Path | What it is |
| --- | --- |
| `policies/*.md` | The 15 policies. Markdown is the source, PDFs are built from it |
| `figures.json` | Data behind the two figures (a bar chart and a bag diagram) |
| `labels.json` | Ground truth: every planted conflict and near miss |
| `corpus.py` | Reads the Markdown into clauses, tables and figures |
| `validate.py` | Checks that every label points at real text |
| `build.py` | Draws the figures into `figures/` and builds PDFs in `build/pdf/` |
| `figures/*.png` | The two chart images, committed so the app can show them |

## Use

```bash
cd evals
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # on macOS or Linux: .venv/bin/pip
cd northwind
../.venv/Scripts/python validate.py               # prints OK when labels match the text
../.venv/Scripts/python build.py                  # needs Microsoft Edge or Chrome
```

`build.py` finds Edge or Chrome on its own. Set `BROWSER` to a browser path to override.

## How the labels work

Each label has two sides, `a` and `b`. A side points at one of three things:

| Kind | Fields | Check |
| --- | --- | --- |
| `clause` | `doc`, `ref` (like `4.1.1`), `quote` | the quote is inside that clause |
| `table` | `doc`, `ref` (like `Table 4.1`), `quote` | a table row, cells joined with ` | `, contains the quote |
| `figure` | `doc`, `ref`, `figure_id`, `key`, `value` | `figures.json` holds that value |

Figure values appear only inside the image. The text around a figure never repeats them, so a scanner has to read the image to find those two conflicts.

## What is planted

| Conflict type | Count |
| --- | --- |
| numeric_mismatch | 13 (6 in text, 5 in tables, 2 in figures) |
| obligation_conflict | 4 |
| definition_mismatch | 3 |
| outdated_reference | 3 |
| scope_overlap | 2 |

Near misses are related clauses that agree: same rule restated, same number written as a word, one policy deferring to another, or a table row that matches while another row in the same table does not (N11).

## Known limits

- The set is 27 pages, below the guide's 60. Add more policies before timing a full scan.
- A conflict that nobody labelled may still exist. If the scanner finds one that looks real, add it to `labels.json` and run `validate.py`.
- Every document has one version. Version and supersede tests need a second version of at least one policy.
