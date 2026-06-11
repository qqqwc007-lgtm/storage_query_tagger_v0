# ruff: noqa: E402
import sys

sys.path = [entry for entry in sys.path if entry not in ("", ".")]

import argparse
import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


CORE_OUTPUTS = (
    "kw.csv",
    "st.csv",
    "diff.csv",
    "review_queue.csv",
    "metrics_summary.json",
)


@dataclass(frozen=True)
class FileSnapshot:
    exists: bool
    size: int | None
    mtime_ns: int | None


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def log(message: str) -> None:
    print(f"[workflow-guard] {message}", flush=True)


def capture(paths: dict[str, Path]) -> dict[str, FileSnapshot]:
    snapshot: dict[str, FileSnapshot] = {}
    for name, path in paths.items():
        if path.exists():
            stat = path.stat()
            snapshot[name] = FileSnapshot(True, stat.st_size, stat.st_mtime_ns)
        else:
            snapshot[name] = FileSnapshot(False, None, None)
    return snapshot


def missing_outputs(paths: dict[str, Path], snapshot: dict[str, FileSnapshot]) -> list[str]:
    return [name for name in paths if not snapshot[name].exists]


def snapshot_changed(
    previous: dict[str, FileSnapshot],
    current: dict[str, FileSnapshot],
) -> bool:
    return any(previous.get(name) != current.get(name) for name in current)


def write_status(path: Path, state: str, **payload: object) -> None:
    status = {"state": state, "updated_at": now_iso(), **payload}
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def build_runner_command(args: argparse.Namespace, passthrough: Iterable[str]) -> list[str]:
    command = [args.python_executable, args.runner_script]
    if args.keyword_input:
        command.extend(["--keyword-input", args.keyword_input])
    if args.top_asin_input:
        command.extend(["--top-asin-input", args.top_asin_input])
    command.extend(["--output-dir", args.output_dir])
    if args.mode:
        command.extend(["--mode", args.mode])
    if args.keyword_chunk_size is not None:
        command.extend(["--keyword-chunk-size", str(args.keyword_chunk_size)])
    if args.title_chunk_size is not None:
        command.extend(["--title-chunk-size", str(args.title_chunk_size)])
    if args.candidate_chunk_size is not None:
        command.extend(["--candidate-chunk-size", str(args.candidate_chunk_size)])
    if args.skip_candidate_discovery:
        command.append("--skip-candidate-discovery")
    command.extend(passthrough)
    return command


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description=(
            "Run the legacy workflow runner under a guard that terminates the "
            "child process once expected outputs stop changing."
        )
    )
    parser.add_argument("--keyword-input")
    parser.add_argument("--top-asin-input")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--mode", default="chunked")
    parser.add_argument("--keyword-chunk-size", type=int, default=100000)
    parser.add_argument("--title-chunk-size", type=int, default=100000)
    parser.add_argument("--candidate-chunk-size", type=int, default=200000)
    parser.add_argument(
        "--skip-candidate-discovery",
        action="store_true",
        help="Stop tracking candidate discovery and treat core outputs as final.",
    )
    parser.add_argument(
        "--allow-missing-candidate-values",
        action="store_true",
        help="Do not wait for candidate_values.csv before terminating a lingering child.",
    )
    parser.add_argument(
        "--runner-script",
        default="scripts/run_workflow.py",
        help="Path to the underlying workflow runner to execute.",
    )
    parser.add_argument(
        "--python-executable",
        default=sys.executable,
        help="Python executable used to start the underlying workflow runner.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=5.0,
        help="How often to re-sample output file mtimes.",
    )
    parser.add_argument(
        "--stabilization-seconds",
        type=float,
        default=90.0,
        help="How long outputs must remain unchanged before the child is terminated.",
    )
    parser.add_argument(
        "--graceful-timeout-seconds",
        type=float,
        default=15.0,
        help="How long to wait after SIGTERM before sending SIGKILL.",
    )
    parser.add_argument(
        "--cwd",
        default=".",
        help="Working directory used when spawning the underlying workflow runner.",
    )
    return parser.parse_known_args()


def main() -> int:
    args, passthrough = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / "workflow_guard_status.json"

    core_paths = {name: output_dir / name for name in CORE_OUTPUTS}
    expected_names = list(CORE_OUTPUTS)
    if not args.skip_candidate_discovery and not args.allow_missing_candidate_values:
        expected_names.append("candidate_values.csv")
    expected_paths = {name: output_dir / name for name in expected_names}

    command = build_runner_command(args, passthrough)
    log(f"starting runner: {' '.join(command)}")
    child_env = os.environ.copy()
    child_env["LC_ALL"] = "en_US.UTF-8"
    child_env["LANG"] = "en_US.UTF-8"
    child_env["PYTHONUTF8"] = "1"
    child = subprocess.Popen(command, cwd=args.cwd, env=child_env)
    write_status(
        status_path,
        "running",
        output_dir=str(output_dir),
        runner_pid=child.pid,
        command=command,
        expected_outputs=expected_names,
        stabilization_seconds=args.stabilization_seconds,
    )

    previous_snapshot = capture(expected_paths)
    last_change_monotonic = time.monotonic()
    core_complete_announced = False

    while True:
        current_snapshot = capture(expected_paths)
        if snapshot_changed(previous_snapshot, current_snapshot):
            last_change_monotonic = time.monotonic()
            previous_snapshot = current_snapshot

        missing_core = missing_outputs(core_paths, capture(core_paths))
        missing_expected = missing_outputs(expected_paths, current_snapshot)
        stable_for = time.monotonic() - last_change_monotonic

        if not core_complete_announced and not missing_core:
            core_complete_announced = True
            log("core outputs are complete")
            write_status(
                status_path,
                "core_outputs_complete",
                output_dir=str(output_dir),
                runner_pid=child.pid,
                missing_outputs=missing_expected,
                expected_outputs=expected_names,
                stable_for_seconds=round(stable_for, 2),
            )

        return_code = child.poll()
        if return_code is not None:
            if return_code == 0 and not missing_expected:
                log("runner exited cleanly")
                write_status(
                    status_path,
                    "completed",
                    output_dir=str(output_dir),
                    runner_pid=child.pid,
                    terminated_runner=False,
                    return_code=return_code,
                    missing_outputs=missing_expected,
                )
                return 0

            if return_code == 0 and not missing_core and args.skip_candidate_discovery:
                log("runner exited after core outputs with candidate discovery skipped")
                write_status(
                    status_path,
                    "completed",
                    output_dir=str(output_dir),
                    runner_pid=child.pid,
                    terminated_runner=False,
                    return_code=return_code,
                    missing_outputs=missing_expected,
                )
                return 0

            log(f"runner exited before outputs stabilized (code={return_code})")
            write_status(
                status_path,
                "runner_exited",
                output_dir=str(output_dir),
                runner_pid=child.pid,
                terminated_runner=False,
                return_code=return_code,
                missing_outputs=missing_expected,
            )
            return return_code

        if not missing_expected and stable_for >= args.stabilization_seconds:
            log(
                "expected outputs are stable; terminating lingering runner "
                f"(stable_for={stable_for:.1f}s)"
            )
            write_status(
                status_path,
                "outputs_stable_terminating_runner",
                output_dir=str(output_dir),
                runner_pid=child.pid,
                missing_outputs=missing_expected,
                stable_for_seconds=round(stable_for, 2),
            )
            child.terminate()
            terminated_with = "SIGTERM"
            try:
                child.wait(timeout=args.graceful_timeout_seconds)
            except subprocess.TimeoutExpired:
                terminated_with = "SIGKILL"
                child.kill()
                child.wait()

            write_status(
                status_path,
                "completed",
                output_dir=str(output_dir),
                runner_pid=child.pid,
                terminated_runner=True,
                termination_signal=terminated_with,
                return_code=child.returncode,
                missing_outputs=missing_expected,
                stable_for_seconds=round(stable_for, 2),
            )
            log(f"guard finished after terminating runner with {terminated_with}")
            return 0

        time.sleep(args.poll_interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
