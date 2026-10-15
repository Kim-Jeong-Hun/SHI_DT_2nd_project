"""Load the existing preprocessing rules without duplicating their calculations."""

from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=None)
def legacy_module(name: str):
    path = PROJECT_ROOT / "scripts" / "전처리" / f"{name}.py"
    if not path.is_file():
        raise FileNotFoundError(path)
    spec = spec_from_file_location(f"ship_orders_legacy_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
