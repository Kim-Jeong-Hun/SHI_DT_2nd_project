"""Combine the five independent holdout evaluations into one comparison."""

import pandas as pd


def display_formatted(table: pd.DataFrame, formats: str | dict[str, str]) -> None:
    """Display a formatted table without requiring the optional Jinja2 Styler."""
    from IPython.display import display

    view = table.copy()
    if isinstance(formats, str):
        formats = {column: formats for column in view.select_dtypes(include="number").columns}
    for column, number_format in formats.items():
        view[column] = view[column].map(
            lambda value: number_format.format(value) if pd.notna(value) else ""
        )
    display(view)


def summarize_holdout(*reports: pd.DataFrame) -> pd.DataFrame:
    if len(reports) != 5 or any(len(report) != 1 for report in reports):
        raise ValueError("Expected one holdout result for each of five vessel types")
    summary = pd.concat(reports, ignore_index=True)
    if summary["선종"].nunique() != 5:
        raise ValueError("Holdout summary has duplicate or missing vessel types")
    return summary.sort_values("sMAPE").reset_index(drop=True)
