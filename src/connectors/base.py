from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass(slots=True)
class BaseConnector:
    name: str
    config: dict[str, Any] = field(default_factory=dict)

    def fetch(self) -> pd.DataFrame:
        raise NotImplementedError
