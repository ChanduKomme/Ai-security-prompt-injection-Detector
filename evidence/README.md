# Evidence

Everything here was produced by running the project; nothing is hand-edited.

| File | What it shows |
|---|---|
| `benchmark.md` / `benchmark.json` | Full benchmark: all modes, all sets, per-category accuracy, mistakes, threshold sweep, gate |
| `test-run.txt` | Verbose output of the 46-test suite |
| `cli-demo.txt` | The CLI on six inputs (attacks in base64, split letters, German; benign trigger words) |
| `screenshots/` | GitHub Actions run, step summary and repository page |

Reproduce: `python3 -m injectscope benchmark` and `python3 -m unittest discover -s tests -v`.
