"""
VizAgent — uses Claude (claude-sonnet-4-6) with tool use to read CSV data
and generate Plotly Express code matching a natural-language description.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import anthropic
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """
You are an expert data-visualization engineer. The user describes a chart they
want, and you produce a **complete, runnable Python code block** that uses
Plotly Express (imported as `px`) and / or `plotly.graph_objects` (imported as
`go`) to build it.

Rules
-----
1. You have three tools: `read_csv`, `get_columns`, and `sample_data`.
   Use them to understand the data before writing code.
2. The generated code must assign the finished figure to a variable called
   `fig` — the executor captures that name.  Do NOT call `fig.show()`.
3. The DataFrame is already loaded in the execution scope as `df`.
   Do NOT re-read the CSV inside the generated code.
4. Only use column names that actually exist in the DataFrame.
5. Return the code inside a single fenced code block:

   ```python
   # your code here
   fig = px.bar(df, ...)
   ```

6. After the code block, add a brief plain-English explanation of the chart.
"""


class VizAgent:
    """Agent that turns a natural-language chart description into Plotly code."""

    # ------------------------------------------------------------------
    # Tool implementations (called locally when Claude requests them)
    # ------------------------------------------------------------------

    @staticmethod
    def _read_csv(path: str) -> str:
        """Return basic info (shape + dtypes) about the CSV."""
        try:
            df = pd.read_csv(path)
            lines = [
                f"Shape: {df.shape[0]} rows × {df.shape[1]} columns",
                "Columns and dtypes:",
            ]
            for col, dtype in df.dtypes.items():
                lines.append(f"  {col!r}: {dtype}")
            return "\n".join(lines)
        except Exception as exc:  # noqa: BLE001
            return f"Error reading CSV: {exc}"

    @staticmethod
    def _get_columns(path: str) -> str:
        """Return just the column names as a JSON list."""
        try:
            df = pd.read_csv(path, nrows=0)
            return json.dumps(list(df.columns))
        except Exception as exc:  # noqa: BLE001
            return f"Error reading CSV columns: {exc}"

    @staticmethod
    def _sample_data(path: str, n: int = 5) -> str:
        """Return the first n rows as a markdown table."""
        try:
            df = pd.read_csv(path, nrows=max(1, n))
            return df.to_markdown(index=False)
        except Exception as exc:  # noqa: BLE001
            return f"Error sampling CSV: {exc}"

    # ------------------------------------------------------------------
    # Tool dispatch helper
    # ------------------------------------------------------------------

    def _execute_tool(self, name: str, tool_input: dict[str, Any]) -> str:
        if name == "read_csv":
            return self._read_csv(tool_input["path"])
        if name == "get_columns":
            return self._get_columns(tool_input["path"])
        if name == "sample_data":
            return self._sample_data(
                tool_input["path"], int(tool_input.get("n", 5))
            )
        return f"Unknown tool: {name}"

    # ------------------------------------------------------------------
    # Tool schema definitions sent to Claude
    # ------------------------------------------------------------------

    TOOLS: list[dict[str, Any]] = [
        {
            "name": "read_csv",
            "description": (
                "Read a CSV file and return its shape plus column names and dtypes."
                " Call this first to understand the dataset structure."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative path to the CSV file.",
                    }
                },
                "required": ["path"],
            },
        },
        {
            "name": "get_columns",
            "description": (
                "Return the column names of a CSV as a JSON list."
                " Useful for a quick lookup without loading full metadata."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the CSV file.",
                    }
                },
                "required": ["path"],
            },
        },
        {
            "name": "sample_data",
            "description": (
                "Return the first n rows of a CSV as a markdown table."
                " Use this to inspect actual data values before writing chart code."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the CSV file.",
                    },
                    "n": {
                        "type": "integer",
                        "description": "Number of rows to return (default 5).",
                        "default": 5,
                    },
                },
                "required": ["path"],
            },
        },
    ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def __init__(self, api_key: str | None = None) -> None:
        self._client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )

    def generate_chart_code(
        self,
        csv_path: str | Path,
        description: str,
        *,
        verbose: bool = False,
    ) -> tuple[str, str]:
        """
        Ask Claude to generate Plotly code for *description* using *csv_path*.

        Returns
        -------
        code : str
            The extracted Python code block (ready to exec).
        explanation : str
            The plain-English explanation Claude provided after the code.
        """
        csv_path = str(csv_path)
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    f"CSV file: {csv_path}\n\n"
                    f"Chart request: {description}"
                ),
            }
        ]

        # Agentic loop — keep going until stop_reason is "end_turn"
        while True:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=self.TOOLS,  # type: ignore[arg-type]
                messages=messages,
            )

            if verbose:
                console.print(
                    f"[dim]stop_reason={response.stop_reason}  "
                    f"blocks={len(response.content)}[/dim]"
                )

            # Append assistant turn
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason != "tool_use":
                # Unexpected stop — bail out gracefully
                break

            # Execute all tool calls and collect results
            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input  # type: ignore[attr-defined]

                if verbose:
                    console.print(
                        f"[bold cyan]Tool call:[/bold cyan] {tool_name}("
                        + ", ".join(f"{k}={v!r}" for k, v in tool_input.items())
                        + ")"
                    )

                result = self._execute_tool(tool_name, tool_input)

                if verbose:
                    console.print(f"[dim]{result[:200]}[/dim]")

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )

            messages.append({"role": "user", "content": tool_results})

        # Extract the code and explanation from the final assistant message
        return self._parse_final_response(messages)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_final_response(
        messages: list[dict[str, Any]],
    ) -> tuple[str, str]:
        """
        Walk the message history backwards to find the last assistant message
        that contains a text block, then extract the fenced code and explanation.
        """
        import re

        full_text = ""
        for msg in reversed(messages):
            if msg["role"] != "assistant":
                continue
            content = msg["content"]
            if isinstance(content, str):
                full_text = content
                break
            # content is a list of block objects or dicts
            for block in content:
                block_type = (
                    block.type if hasattr(block, "type") else block.get("type")
                )
                if block_type == "text":
                    text = (
                        block.text
                        if hasattr(block, "text")
                        else block.get("text", "")
                    )
                    full_text += text
            if full_text:
                break

        # Extract fenced python block
        pattern = r"```python\s*\n(.*?)\n```"
        match = re.search(pattern, full_text, re.DOTALL)
        if not match:
            # Fallback: return everything as code if no fence found
            return full_text.strip(), ""

        code = match.group(1).strip()

        # Everything after the closing fence is the explanation
        after_fence = full_text[match.end():].strip()

        return code, after_fence
