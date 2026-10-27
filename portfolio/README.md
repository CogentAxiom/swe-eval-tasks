# Portfolio pages

The files in this folder are web pages. GitHub's file view shows HTML as source code, so open them rendered, on
GitHub Pages:

| Page | Open it rendered |
|---|---|
| Front page: a summary of all three exhibits (`index.html`) | [cogentaxiom.github.io/swe-eval-tasks/portfolio/](https://cogentaxiom.github.io/swe-eval-tasks/portfolio/) |
| Exhibit 1: the ERCOT engine (`engine.html`) | [engine.html](https://cogentaxiom.github.io/swe-eval-tasks/portfolio/engine.html) |
| Exhibit 2: the Audit Rubric (`audit-rubric.html`) | [audit-rubric.html](https://cogentaxiom.github.io/swe-eval-tasks/portfolio/audit-rubric.html) |
| Exhibit 2: Where an Error Goes, the decision tree and every definition (`decision-tree.html`) | [decision-tree.html](https://cogentaxiom.github.io/swe-eval-tasks/portfolio/decision-tree.html) |

Exhibit 3, the eval tasks, has no page of its own. Its write-ups are Markdown and render here on GitHub:
[exhibit-3-eval-tasks/](../exhibit-3-eval-tasks/).

**How the pages are made.**
- **Exhibit 2 pages:** generated from the build outputs by
  [`build_page.py`](../exhibit-2-failure-taxonomy/auditkit/tools/build_page.py) and
  [`build_tree_page.py`](../exhibit-2-failure-taxonomy/auditkit/tools/build_tree_page.py), so every number on them
  comes from a build.
- **Engine page:** generated from the engine's own artifacts.
- **Front page:** written by hand.
