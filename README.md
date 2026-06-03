# viz-agent-ai

**Natural language to chart** — describe what you want, get a runnable Plotly chart back.

viz-agent uses Claude (`claude-sonnet-4-6`) as its brain.  Claude inspects your
CSV through a small set of read-only tools, writes Plotly Express code that
matches your description, and the executor runs the code and saves the figure.

---

## Quick start

```bash
# Install (Python 3.10+)
pip install viz-agent-ai

# Or from source
git clone https://github.com/example/viz-agent-ai
cd viz-agent-ai
pip install -e .
```

Set your Anthropic API key:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Generate a chart:

```bash
viz-agent chart sales.csv "show monthly revenue as a bar chart grouped by region" \
    --output chart.html
```

Open `chart.html` in any browser.

---

## CLI reference

```
Usage: viz-agent chart [OPTIONS] CSV DESCRIPTION

  Generate a Plotly chart from a CSV file and a plain-English DESCRIPTION.

Arguments:
  CSV          Path to the input CSV file.
  DESCRIPTION  Natural-language chart request.

Options:
  -o, --output PATH  Output file path. Extension sets format: .html,
                     .png, .svg, .pdf.  [default: chart.html]
  -v, --verbose      Print tool calls and intermediate messages.
  -s, --show-code    Print the generated Python code to the terminal.
  --help             Show this message and exit.
```

### Examples

```bash
# Interactive HTML (default — no extra dependencies)
viz-agent chart data.csv "scatter plot of price vs rating, colored by category"

# Show the generated code
viz-agent chart data.csv "line chart of daily active users over time" --show-code

# Save as PNG (requires kaleido: pip install kaleido)
viz-agent chart data.csv "top 10 products by revenue as a horizontal bar" \
    --output chart.png

# Verbose mode — see which tools Claude calls
viz-agent chart data.csv "heatmap of correlation between numeric columns" \
    --verbose --show-code
```

---

## Python API

### `VizAgent`

```python
from viz_agent import VizAgent, CodeExecutor

agent = VizAgent()   # reads ANTHROPIC_API_KEY from env

# Generate Plotly code
code, explanation = agent.generate_chart_code(
    "sales.csv",
    "monthly revenue bar chart grouped by region",
    verbose=True,          # optional: print tool calls
)

print(explanation)   # Claude's plain-English description
print(code)          # Python code block ready to exec
```

### `CodeExecutor`

```python
executor = CodeExecutor("sales.csv")

# Just run the code and get a Plotly figure back
fig = executor.run(code)
fig.show()           # open in browser

# Or save directly
output = executor.save(code, "chart.html")      # interactive HTML
output = executor.save(code, "chart.png")       # static PNG (kaleido required)
output = executor.save(code, "chart.svg")       # vector SVG (kaleido required)
```

---

## How it works

```
User describes chart
        │
        ▼
  VizAgent sends description + CSV path to Claude
        │
        ▼
  Claude calls tools to inspect the data:
    ├── read_csv(path)          → shape + column dtypes
    ├── get_columns(path)       → column names as JSON list
    └── sample_data(path, n)   → first n rows as markdown table
        │
        ▼
  Claude returns a fenced Python code block
        │
        ▼
  CodeExecutor.run(code)
    • loads DataFrame as `df`
    • makes `px`, `go`, `pd` available
    • exec()s the code
    • captures `fig`
        │
        ▼
  fig.write_html(...)  or  fig.write_image(...)
```

### Tools Claude can use

| Tool | Description |
|---|---|
| `read_csv(path)` | Shape and column dtypes |
| `get_columns(path)` | Column names as a JSON list |
| `sample_data(path, n)` | First *n* rows as a markdown table |

All tools are read-only — they never mutate the file.

---

## Static image export (PNG / SVG / PDF)

Static formats require the `kaleido` package:

```bash
pip install kaleido
# or install the optional extra:
pip install viz-agent-ai[static]
```

---

## Development

```bash
git clone https://github.com/example/viz-agent-ai
cd viz-agent-ai
pip install -e '.[dev]'

# Lint
ruff check viz_agent/

# Type-check
mypy viz_agent/

# Tests
pytest
```

---

## License

MIT
