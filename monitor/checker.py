import time
import requests
from dataclasses import dataclass

@dataclass
class CheckResult:
    url: str
    ok: bool
    status_code: int | None
    response_time_ms: float
    error: str | None = None

def check_site(url: str, timeout: float = 10.0) -> CheckResult:
    start = time.perf_counter()
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "SiteMonitor/1.0"},
            allow_redirects=True,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        return CheckResult(
            url=url,
            ok=True,
            status_code=response.status_code,
            response_time_ms=round(elapsed_ms, 1),
        )
    except requests.RequestException as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return CheckResult(
            url=url,
            ok=False,
            status_code=None,
            response_time_ms=round(elapsed_ms, 1),
            error=str(exc),
        )
    # checker.py
def check_site(cfg: dict) -> CheckResult:
    url = cfg["url"]
    start = time.perf_counter()
    try:
        response = requests.request(
            cfg.get("method", "GET"),
            url,
            timeout=cfg.get("timeout_sec", 10.0),
            headers={"User-Agent": "SiteMonitor/1.0"},
            allow_redirects=True,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        ok = True
        error = None
        if cfg.get("expected_status") is not None:
            ok = response.status_code == cfg["expected_status"]
            if not ok:
                error = f"ожидался {cfg['expected_status']}"
        else:
            ok = 200 <= response.status_code < 400
            if not ok:
                error = f"неожиданный статус {response.status_code}"

        if ok and cfg.get("keyword"):
            if cfg["keyword"] not in response.text:
                ok = False
                error = f"нет ключевого слова «{cfg['keyword']}»"

        return CheckResult(url, ok, response.status_code, round(elapsed_ms, 1), error)
    except requests.RequestException as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return CheckResult(url, False, None, round(elapsed_ms, 1), str(exc))