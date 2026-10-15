"""Fetch 2026 monthly commodity-trade observations from the UN Comtrade API.

The public preview endpoint is queried one commodity/month at a time. These
are current-vintage reported observations, not reconstructed historical vintages.
Existing pre-2026 raw files are never overwritten.
"""

from __future__ import annotations

import csv
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "물동량"
BASE = "https://comtradeapi.un.org/public/v1/preview/C/M/HS"
SERIES = {
    "대두유 무역량": ("1507", "M"),
    "면화 무역량": ("5201", "M"),
    "일본 LNG 무역량": ("271111", "M"),
    "천연고무 무역량": ("4001", "M"),
    "천연고무 TSR20 무역량": ("400122", "M"),
    "철광석 무역량": ("2601", "M"),
    "팜유 무역량": ("1511", "M"),
    "호주 석탄 무역량": ("2701", "X"),
}
MONTHS = [f"2026{month:02d}" for month in range(1, 9)]


def fetch(code: str, flow: str, month: str) -> tuple[list[dict], str]:
    parameters = {
        "period": month, "cmdCode": code, "flowCode": flow,
        "partnerCode": 0, "maxRecords": 500,
    }
    url = f"{BASE}?{urlencode(parameters)}"
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": "ship-orders-forecasting/1.0"}),
                         timeout=90) as response:
                payload = json.load(response)
            rows = payload.get("data", [])
            if not isinstance(rows, list) or payload.get("count") != len(rows):
                raise ValueError(f"응답 잘림·형식 오류: {code}/{flow}/{month}")
            return rows, url
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, (code, flow) in SERIES.items():
        observations: list[dict] = []
        month_counts: dict[str, int] = {}
        urls: list[str] = []
        for month in MONTHS:
            rows, url = fetch(code, flow, month)
            # The API response lacks ISO labels in some recent observations.
            # Only Japan/Australia are filtered by reporter in preprocessing.
            for row in rows:
                if row.get("reporterCode") == 392:
                    row["reporterISO"] = "JPN"
                elif row.get("reporterCode") == 36:
                    row["reporterISO"] = "AUS"
            observations.extend(rows)
            month_counts[month] = len(rows)
            urls.append(url)
            print(name, month, len(rows), flush=True)
            time.sleep(0.15)
        if not observations:
            continue
        path = OUT / f"{name}_2026.csv"
        columns = list(dict.fromkeys(key for row in observations for key in row))
        temporary = path.with_suffix(".csv.download")
        with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(observations)
        temporary.replace(path)
        manifest.append({
            "파일": path.name, "원천": "UN Comtrade public preview API",
            "원천페이지": "https://uncomtrade.org/docs/un-comtrade-api/",
            "질의URL": urls, "월별레코드수": month_counts,
            "다운로드시각UTC": datetime.now(timezone.utc).isoformat(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "주의": "현재 공개 빈티지이며 국가별 보고 지연으로 글로벌 합계가 잠정·불완전할 수 있음",
        })
    record = OUT / "UNComtrade_2026_수집기록.json"
    record.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
