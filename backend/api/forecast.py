import pathlib
import sys

from fastapi import FastAPI, HTTPException, Query


BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNTIME_ROOT = BACKEND_ROOT / "forecast_runtime"
sys.path.insert(0, str(BACKEND_ROOT))

from forecast_engine import config as custom_forecast_config  # noqa: E402
from forecast_engine import run as run_custom_forecast  # noqa: E402


app = FastAPI(title="ShipPulse Custom Forecast")


@app.get("/api/forecast")
def health():
    return {"ok": True}


@app.post("/api/forecast")
def forecast(payload: dict, action: str = Query(..., pattern="^(config|run)$")):
    try:
        if action == "config":
            return custom_forecast_config(RUNTIME_ROOT, payload.get("vesselId"))
        return run_custom_forecast(RUNTIME_ROOT, payload)
    except (KeyError, TypeError, ValueError, FileNotFoundError) as error:
        raise HTTPException(400, str(error)) from error
