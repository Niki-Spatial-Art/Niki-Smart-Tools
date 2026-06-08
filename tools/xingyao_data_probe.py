import json
import os
import subprocess
import sys
import traceback
import uuid
from datetime import datetime
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
JSON_BEGIN = "___XINGYAO_PROBE_JSON_BEGIN___"
JSON_END = "___XINGYAO_PROBE_JSON_END___"
DEFAULT_WORKER_JSON = PROJECT_ROOT / "data" / "latest_xingyao_worker_result.json"
DEFAULT_WORKER_PROGRESS = PROJECT_ROOT / "data" / "latest_xingyao_worker_progress.log"
WORKER_JSON = Path(os.getenv("XINGYAO_WORKER_JSON", str(DEFAULT_WORKER_JSON)))
WORKER_PROGRESS = Path(os.getenv("XINGYAO_WORKER_PROGRESS", str(DEFAULT_WORKER_PROGRESS)))


def _progress(message: str) -> None:
    WORKER_PROGRESS.parent.mkdir(exist_ok=True)
    with WORKER_PROGRESS.open("a", encoding="utf-8") as handle:
        handle.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def _run_worker() -> int:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    import monitor

    WORKER_JSON.parent.mkdir(exist_ok=True)
    WORKER_PROGRESS.write_text("", encoding="utf-8")
    run_id = os.getenv("XINGYAO_PROBE_RUN_ID", "")
    _progress(f"worker started run_id={run_id}")

    sample_codes = [
        code.strip()
        for code in os.getenv("XINGYAO_PROBE_CODES", "510300,588000,512100,510050,600498").split(",")
        if code.strip()
    ]

    _progress("checking sdk capabilities")
    capabilities = monitor.xingyao_sdk_capabilities()

    _progress("loading option basic cache")
    option_status = monitor.load_xingyao_option_cache() or {}
    if not option_status:
        _progress("fetching option basic rows")
        option_status = monitor.fetch_xingyao_option_basic_rows()

    _progress("fetching snapshot rows")
    snapshot_status = monitor.fetch_xingyao_snapshot_rows(sample_codes)

    if monitor.env_enabled("XINGYAO_KLINE_PROBE_ENABLED", "false"):
        _progress("fetching kline rows")
        kline_status = monitor.fetch_xingyao_kline_probe(sample_codes)
    else:
        kline_status = {
            "enabled": False,
            "source": "xingyao_kline",
            "row_count": 0,
            "error": "disabled by XINGYAO_KLINE_PROBE_ENABLED=false",
        }

    active_sources = []
    if option_status.get("contract_count", 0):
        active_sources.append("xingyao_option_basic")
    if snapshot_status.get("row_count", 0):
        active_sources.append("xingyao_snapshot")
    if kline_status.get("row_count", 0):
        active_sources.append("xingyao_kline")

    result = {
        "run_id": run_id,
        "enabled": monitor.env_enabled("XINGYAO_ENABLED", "false"),
        "quote_priority_enabled": monitor.env_enabled("XINGYAO_QUOTE_PRIORITY", "false"),
        "sample_codes": sample_codes,
        "active_sources": active_sources,
        "capabilities": capabilities,
        "option_basic": {
            "source": option_status.get("source", ""),
            "contract_count": option_status.get("contract_count", 0),
            "cache_used": option_status.get("cache_used", False),
            "cache_updated_at": option_status.get("cache_updated_at", ""),
            "error": option_status.get("error", ""),
        },
        "snapshot_probe": {
            "source": snapshot_status.get("source", ""),
            "requested": snapshot_status.get("requested", []),
            "row_count": snapshot_status.get("row_count", 0),
            "sample_rows": (snapshot_status.get("rows") or [])[:3],
            "error": snapshot_status.get("error", ""),
        },
        "kline_probe": {
            "source": kline_status.get("source", ""),
            "requested": kline_status.get("requested", []),
            "row_count": kline_status.get("row_count", 0),
            "sample_rows": (kline_status.get("rows") or [])[:3],
            "error": kline_status.get("error", ""),
        },
        "recommendation": (
            "Xingyao snapshot/K-line returned data; validate fields before enabling quote priority."
            if snapshot_status.get("row_count", 0) or kline_status.get("row_count", 0)
            else "Xingyao realtime snapshot/K-line did not return usable data. Keep Eastmoney/Sina/Tencent fallback."
        ),
    }
    _progress("writing worker result")
    WORKER_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    _progress("worker finished")

    print(JSON_BEGIN)
    print(json.dumps(result, ensure_ascii=False, default=str))
    print(JSON_END)
    return 0


def _extract_json(stdout: str) -> dict:
    start = stdout.find(JSON_BEGIN)
    end = stdout.find(JSON_END)
    if start < 0 or end < 0 or end <= start:
        raise ValueError("worker did not return JSON markers")
    payload = stdout[start + len(JSON_BEGIN):end].strip()
    return json.loads(payload)


def _fallback_result(error: str, stdout: str = "", stderr: str = "", returncode=None) -> dict:
    detail = error
    if returncode is not None:
        detail += f"; worker_returncode={returncode}"
    if stderr.strip():
        detail += f"; stderr={stderr.strip()[-1200:]}"
    if stdout.strip():
        detail += f"; stdout={stdout.strip()[-1200:]}"
    return {
        "enabled": True,
        "active_sources": [],
        "capabilities": {},
        "option_basic": {"contract_count": 0, "error": detail},
        "snapshot_probe": {"row_count": 0, "error": detail},
        "kline_probe": {"row_count": 0, "error": detail},
        "recommendation": "Xingyao probe failed. Keep Eastmoney/Sina/Tencent fallback and do not enable Xingyao quote priority.",
    }


def _status_label(rows: int, error: str = "") -> str:
    if rows:
        return f"OK ({rows})"
    if error:
        return f"NO DATA - {error}"
    return "NO DATA"


def main() -> int:
    global WORKER_JSON, WORKER_PROGRESS

    timeout_seconds = int(os.getenv("XINGYAO_PROBE_TIMEOUT_SECONDS", "45"))
    run_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
    out_dir = PROJECT_ROOT / "data"
    out_dir.mkdir(exist_ok=True)
    WORKER_JSON = out_dir / f"xingyao_worker_result_{run_id}.json"
    WORKER_PROGRESS = out_dir / f"xingyao_worker_progress_{run_id}.log"
    print(f"Starting Xingyao data probe, timeout={timeout_seconds}s ...", flush=True)

    stdout = ""
    stderr = ""
    probe_error = ""
    try:
        for stale_path in (WORKER_JSON, WORKER_PROGRESS):
            if stale_path.exists():
                try:
                    stale_path.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    # A previous worker/file watcher may still hold the file.
                    # Keep running; the run_id check below prevents stale reads.
                    pass
        child_env = os.environ.copy()
        child_env["XINGYAO_PROBE_RUN_ID"] = run_id
        child_env["XINGYAO_WORKER_JSON"] = str(WORKER_JSON)
        child_env["XINGYAO_WORKER_PROGRESS"] = str(WORKER_PROGRESS)
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--worker"],
            cwd=str(PROJECT_ROOT),
            env=child_env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_seconds,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        worker_file_result = None
        if WORKER_JSON.exists():
            try:
                worker_file_result = json.loads(WORKER_JSON.read_text(encoding="utf-8"))
            except Exception:
                worker_file_result = None
        if completed.returncode != 0:
            probe_error = f"worker failed with exit code {completed.returncode}"
            result = _fallback_result(probe_error, stdout, stderr, completed.returncode)
        else:
            try:
                result = _extract_json(stdout)
            except Exception as exc:
                if worker_file_result and worker_file_result.get("run_id") == run_id:
                    probe_error = f"{exc}; recovered result from worker file"
                    result = worker_file_result
                else:
                    probe_error = str(exc)
                    result = _fallback_result(probe_error, stdout, stderr, completed.returncode)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        probe_error = f"Timed out after {timeout_seconds}s"
        result = _fallback_result(probe_error, stdout, stderr)
    except Exception as exc:
        probe_error = str(exc)
        result = _fallback_result(traceback.format_exc())

    out_path = out_dir / "latest_xingyao_data_probe.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    log_path = out_dir / "latest_xingyao_data_probe.log"
    log_path.write_text(
        "STDOUT:\n"
        + stdout
        + "\n\nSTDERR:\n"
        + stderr
        + "\n\nWORKER_PROGRESS:\n"
        + (WORKER_PROGRESS.read_text(encoding="utf-8") if WORKER_PROGRESS.exists() else "")
        + "\n",
        encoding="utf-8",
    )

    capabilities = result.get("capabilities", {})
    option_basic = result.get("option_basic", {})
    snapshot = result.get("snapshot_probe", {})
    kline = result.get("kline_probe", {})

    print("")
    print("=== Xingyao data probe ===")
    if probe_error:
        print(f"Probe status: {probe_error}")
    print(f"AmazingData SDK import: {'OK' if capabilities.get('amazingdata_import') else 'FAILED'}")
    print(f"TGW SDK import: {'OK' if capabilities.get('tgw_import') else 'FAILED'}")
    if capabilities.get("sdk_error"):
        print(f"SDK error: {capabilities.get('sdk_error')}")
    print(f"Option basic contracts: {_status_label(int(option_basic.get('contract_count') or 0), option_basic.get('error') or '')}")
    print(f"ETF/A-share snapshot: {_status_label(int(snapshot.get('row_count') or 0), snapshot.get('error') or '')}")
    print(f"K-line probe: {_status_label(int(kline.get('row_count') or 0), kline.get('error') or '')}")
    print(f"Active sources: {', '.join(result.get('active_sources') or []) or 'none'}")
    print(f"Recommendation: {result.get('recommendation') or 'No recommendation returned.'}")
    print(f"Saved JSON: {out_path}")
    print(f"Saved log: {log_path}")
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("")

    return 0 if capabilities.get("amazingdata_import") else 1


if __name__ == "__main__":
    if "--worker" in sys.argv:
        raise SystemExit(_run_worker())
    raise SystemExit(main())
