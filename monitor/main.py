from checker import check_site
from config import SITES, TIMEOUT

for cfg in sites:
    if not cfg.get("enabled", True):
        continue
    result = check_site(cfg)
    icon = cfg.get("icon", "🌐")
    print(f"{icon} {cfg['name']}: HTTP {result.status_code} — {result.response_time_ms} ms")

def format_result(result) -> str:
    if not result.ok:
        return f"❌ DOWN  {result.url}  ({result.error})"
    status_icon = "✅" if 200 <= result.status_code < 400 else "⚠️"
    return (
        f"{status_icon} UP    {result.url}  "
        f"HTTP {result.status_code}  {result.response_time_ms} ms"
    )

def run_once() -> None:
    for url in SITES:
        result = check_site(url, timeout=TIMEOUT)
        print(format_result(result))

if __name__ == "__main__":
    run_once()