"""
CodeExecutor — safely executes generated Plotly code and saves the output.
"""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

import pandas as pd


class ExecutionError(RuntimeError):
    """Raised when generated code fails to execute cleanly."""


class CodeExecutor:
    """
    Execute a snippet of Plotly code produced by VizAgent.

    The snippet runs in an isolated namespace that has:
    * ``df``  — the DataFrame loaded from the CSV
    * ``px``  — plotly.express
    * ``go``  — plotly.graph_objects
    * ``pd``  — pandas

    After execution the ``fig`` variable is captured and can be
    saved to HTML or PNG.
    """

    def __init__(self, csv_path: str | Path) -> None:
        self._csv_path = Path(csv_path)
        if not self._csv_path.exists():
            raise FileNotFoundError(f"CSV not found: {self._csv_path}")
        self._df = pd.read_csv(self._csv_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, code: str) -> Any:
        """
        Execute *code* in a sandboxed namespace.

        Returns the ``fig`` object produced by the code.

        Raises
        ------
        ExecutionError
            If execution fails or ``fig`` is not assigned.
        """
        import plotly.express as px  # noqa: F401 — available in exec scope
        import plotly.graph_objects as go  # noqa: F401 — available in exec scope

        namespace: dict[str, Any] = {
            "df": self._df.copy(),
            "px": px,
            "go": go,
            "pd": pd,
        }

        try:
            exec(code, namespace)  # noqa: S102
        except Exception as exc:
            tb = traceback.format_exc()
            raise ExecutionError(
                f"Generated code raised an exception:\n{tb}"
            ) from exc

        if "fig" not in namespace:
            raise ExecutionError(
                "Generated code did not assign a variable named `fig`."
            )

        return namespace["fig"]

    def save(
        self,
        code: str,
        output_path: str | Path,
        *,
        width: int = 1200,
        height: int = 700,
        scale: float = 2.0,
    ) -> Path:
        """
        Execute *code*, then write the figure to *output_path*.

        Supported formats (detected from the file extension):

        * ``.html`` — interactive HTML (no extra dependencies)
        * ``.png``  — static PNG raster  (requires *kaleido*)
        * ``.svg``  — vector SVG         (requires *kaleido*)
        * ``.pdf``  — PDF                (requires *kaleido*)
        * ``.jpg`` / ``.jpeg`` — JPEG    (requires *kaleido*)

        Returns the resolved output path.
        """
        fig = self.run(code)
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        suffix = output_path.suffix.lower()

        if suffix == ".html":
            fig.write_html(str(output_path))
        elif suffix in (".png", ".svg", ".pdf", ".jpg", ".jpeg"):
            self._save_static(
                fig, output_path, width=width, height=height, scale=scale
            )
        else:
            raise ValueError(
                f"Unsupported output format '{suffix}'. "
                "Use .html, .png, .svg, .pdf, or .jpg."
            )

        return output_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _save_static(
        fig: Any,
        path: Path,
        width: int,
        height: int,
        scale: float,
    ) -> None:
        """Write a static image using kaleido."""
        try:
            fig.write_image(
                str(path),
                width=width,
                height=height,
                scale=scale,
            )
        except ValueError as exc:
            # kaleido not installed — surface a helpful message
            if "kaleido" in str(exc).lower() or "orca" in str(exc).lower():
                raise RuntimeError(
                    "Static image export requires the 'kaleido' package.\n"
                    "Install it with:  pip install kaleido"
                ) from exc
            raise
