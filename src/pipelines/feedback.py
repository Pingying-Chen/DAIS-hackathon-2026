from __future__ import annotations

from typing import Sequence

import pandas as pd


def _key_value(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def append_only_frame(candidate: pd.DataFrame, existing: pd.DataFrame, key_columns: Sequence[str]) -> pd.DataFrame:
    if candidate.empty:
        return candidate.copy()
    missing_candidate_columns = [column for column in key_columns if column not in candidate]
    if missing_candidate_columns:
        raise ValueError(f"candidate is missing key columns: {', '.join(missing_candidate_columns)}")
    if existing.empty:
        return candidate.drop_duplicates(list(key_columns)).reset_index(drop=True)

    missing_existing_columns = [column for column in key_columns if column not in existing]
    if missing_existing_columns:
        return candidate.drop_duplicates(list(key_columns)).reset_index(drop=True)

    existing_keys = {
        tuple(_key_value(row[column]) for column in key_columns)
        for _, row in existing.iterrows()
    }
    keep_mask = candidate.apply(
        lambda row: tuple(_key_value(row[column]) for column in key_columns) not in existing_keys,
        axis=1,
    )
    return candidate[keep_mask].drop_duplicates(list(key_columns)).reset_index(drop=True)
