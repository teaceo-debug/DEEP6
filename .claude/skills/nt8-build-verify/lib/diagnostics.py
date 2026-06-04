import dataclasses
import datetime
import json
import pathlib
import shutil
import time
import uuid


@dataclasses.dataclass
class CompileError:
    code: str
    message: str
    file: str
    line: int
    col: int
    severity: str


@dataclasses.dataclass
class FixResult:
    error: CompileError
    fix_applied: str
    diff: str
    success: bool
    rollback_needed: bool


def generate_run_id() -> str:
    now = datetime.datetime.now()
    hex_suffix = uuid.uuid4().hex[:4]
    return f"bv-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}-{hex_suffix}"


def parse_sentinel(line: str):
    prefix = "[COMPILE-RESULT] "
    if not line.startswith(prefix):
        return None

    payload = line[len(prefix) :].strip()
    if not payload:
        return None

    parts = payload.split(maxsplit=1)
    status = parts[0]
    if len(parts) == 1:
        return {"status": status}

    detail = parts[1]
    if status == "SUCCESS":
        return {"status": "SUCCESS", "timestamp": detail}
    if status == "FAILED":
        return {"status": "FAILED", "reason": detail}
    return {"status": status, "detail": detail}


class RunArtifacts:
    def __init__(self, base_dir: str = "./artifacts"):
        self.run_id = generate_run_id()
        self.run_dir = pathlib.Path(base_dir) / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def save_json(self, name: str, data: dict) -> pathlib.Path:
        path = self.run_dir / f"{name}.json"
        path.write_text(json.dumps(data, indent=2, default=str))
        return path

    def save_text(self, name: str, text: str) -> pathlib.Path:
        path = self.run_dir / name
        path.write_text(text)
        return path

    def save_screenshot(self, name: str, source_path: str) -> pathlib.Path:
        dest = self.run_dir / name
        shutil.copy2(source_path, dest)
        return dest

    def get_run_dir(self) -> pathlib.Path:
        return self.run_dir


class Timer:
    def __init__(self, phase_name: str):
        self.phase_name = phase_name
        self.elapsed_ms = 0

    def __enter__(self):
        self._start = time.time()
        return self

    def __exit__(self, *args):
        self.elapsed_ms = int((time.time() - self._start) * 1000)


EXIT_CODES = {
    "SUCCESS": 0,
    "ERRORS": 1,
    "INFRASTRUCTURE": 2,
    "MAX_ITERATIONS": 3,
}
