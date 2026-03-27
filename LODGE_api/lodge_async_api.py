import shutil
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field


APP_ROOT = Path(__file__).resolve().parent
DEFAULT_TASK_ROOT = APP_ROOT / "task_runs"
DEFAULT_TASK_ROOT.mkdir(parents=True, exist_ok=True)


class RenderSongRequest(BaseModel):
    lodge_root: str = Field(..., description="LODGE project root path, e.g. D:/LODGE-main")
    sample_dir: str = Field(..., description="Inference sample dir containing concat/npy, e.g. .../samples_dod_xxx")
    song_id: str = Field(..., description="Song id like 132")
    python_executable: Optional[str] = Field(default=sys.executable, description="Python executable in lodge conda env")
    mode: str = Field(default="smplx", pattern="^(smpl|smplh|smplx)$")
    device: str = Field(default="0", description="GPU device id string")
    fps: int = Field(default=30, ge=1, le=120)


class InferAndRenderRequest(BaseModel):
    lodge_root: str = Field(..., description="LODGE project root path, e.g. D:/LODGE-main")
    song_id: str = Field(..., description="Song id like 132")
    python_executable: Optional[str] = Field(default=sys.executable, description="Python executable in lodge conda env")
    infer_args: List[str] = Field(
        default_factory=list,
        description="Extra args passed to infer_lodge.py, e.g. ['--soft', '1.0']",
    )
    sample_dir_hint: Optional[str] = Field(
        default=None,
        description="Optional explicit sample dir. If omitted, API auto-detects latest samples_dod_* dir",
    )
    mode: str = Field(default="smplx", pattern="^(smpl|smplh|smplx)$")
    device: str = Field(default="0", description="GPU device id string")
    fps: int = Field(default=30, ge=1, le=120)


class TaskInfo(BaseModel):
    task_id: str
    status: str
    created_at: str
    updated_at: str
    message: str = ""
    output_mp4_path: Optional[str] = None
    stdout_tail: str = ""
    stderr_tail: str = ""


app = FastAPI(title="LODGE Async API", version="1.0.0")
executor = ThreadPoolExecutor(max_workers=2)
_tasks: Dict[str, TaskInfo] = {}
_task_lock = threading.Lock()


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _tail_text(text: str, max_chars: int = 6000) -> str:
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _update_task(task_id: str, **kwargs) -> None:
    with _task_lock:
        task = _tasks.get(task_id)
        if task is None:
            return
        data = task.model_dump()
        data.update(kwargs)
        data["updated_at"] = _utc_now()
        _tasks[task_id] = TaskInfo(**data)


def _find_rendered_mp4(video_dir: Path, song_id: str) -> Path:
    if not video_dir.exists():
        raise FileNotFoundError(f"Render output dir not found: {video_dir}")

    candidates = sorted(video_dir.glob(f"{song_id}*.mp4"))
    if not candidates:
        # Fallback: return latest mp4 in case naming changes.
        candidates = sorted(video_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)

    if not candidates:
        raise FileNotFoundError(f"No mp4 generated under: {video_dir}")

    return candidates[-1]


def _detect_latest_sample_dir(lodge_root: Path) -> Path:
    experiments_root = lodge_root / "experiments"
    if not experiments_root.exists():
        raise FileNotFoundError(f"experiments dir not found: {experiments_root}")

    candidates = [
        p for p in experiments_root.rglob("samples_dod_*") if p.is_dir() and (p / "concat" / "npy").exists()
    ]
    if not candidates:
        raise FileNotFoundError("No samples_dod_* dir with concat/npy found under experiments")

    candidates.sort(key=lambda p: p.stat().st_mtime)
    return candidates[-1]


def _run_command(command: List[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _render_from_sample_dir(task_id: str, lodge_root: Path, sample_dir: Path, song_id: str, python_exe: str, mode: str, device: str, fps: int) -> None:
    source_npy = sample_dir / "concat" / "npy" / f"{song_id}.npy"
    if not source_npy.exists():
        raise FileNotFoundError(f"Source npy not found: {source_npy}")

    task_root = DEFAULT_TASK_ROOT / task_id
    input_dir = task_root / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    target_npy = input_dir / f"{song_id}.npy"
    shutil.copy2(source_npy, target_npy)

    render_command = [
        python_exe,
        "render.py",
        "--modir",
        str(input_dir),
        "--mode",
        mode,
        "--device",
        device,
        "--fps",
        str(fps),
    ]

    proc = _run_command(render_command, lodge_root)
    stdout_tail = _tail_text(proc.stdout or "")
    stderr_tail = _tail_text(proc.stderr or "")

    if proc.returncode != 0:
        _update_task(
            task_id,
            status="failed",
            message=f"render.py failed with return code {proc.returncode}",
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
        )
        return

    video_dir = input_dir / "video"
    output_mp4 = _find_rendered_mp4(video_dir, song_id)

    _update_task(
        task_id,
        status="succeeded",
        message="Task completed",
        output_mp4_path=str(output_mp4.resolve()),
        stdout_tail=stdout_tail,
        stderr_tail=stderr_tail,
    )


def _run_render_task(task_id: str, req: RenderSongRequest) -> None:
    try:
        _update_task(task_id, status="running", message="Task is running")

        lodge_root = Path(req.lodge_root).resolve()
        sample_dir = Path(req.sample_dir).resolve()

        if not lodge_root.exists():
            raise FileNotFoundError(f"lodge_root not found: {lodge_root}")
        if not sample_dir.exists():
            raise FileNotFoundError(f"sample_dir not found: {sample_dir}")

        _render_from_sample_dir(
            task_id=task_id,
            lodge_root=lodge_root,
            sample_dir=sample_dir,
            song_id=req.song_id,
            python_exe=req.python_executable or sys.executable,
            mode=req.mode,
            device=req.device,
            fps=req.fps,
        )

    except Exception as exc:
        _update_task(task_id, status="failed", message=str(exc))


def _run_infer_and_render_task(task_id: str, req: InferAndRenderRequest) -> None:
    try:
        _update_task(task_id, status="running", message="Running infer_lodge.py")

        lodge_root = Path(req.lodge_root).resolve()
        if not lodge_root.exists():
            raise FileNotFoundError(f"lodge_root not found: {lodge_root}")

        infer_command = [req.python_executable or sys.executable, "infer_lodge.py"] + req.infer_args
        infer_proc = _run_command(infer_command, lodge_root)
        infer_stdout = _tail_text(infer_proc.stdout or "")
        infer_stderr = _tail_text(infer_proc.stderr or "")

        if infer_proc.returncode != 0:
            _update_task(
                task_id,
                status="failed",
                message=f"infer_lodge.py failed with return code {infer_proc.returncode}",
                stdout_tail=infer_stdout,
                stderr_tail=infer_stderr,
            )
            return

        _update_task(task_id, message="Inference done, rendering mp4")

        sample_dir = Path(req.sample_dir_hint).resolve() if req.sample_dir_hint else _detect_latest_sample_dir(lodge_root)
        _render_from_sample_dir(
            task_id=task_id,
            lodge_root=lodge_root,
            sample_dir=sample_dir,
            song_id=req.song_id,
            python_exe=req.python_executable or sys.executable,
            mode=req.mode,
            device=req.device,
            fps=req.fps,
        )

    except Exception as exc:
        _update_task(task_id, status="failed", message=str(exc))


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/lodge/tasks/render-song", response_model=TaskInfo)
def create_render_song_task(req: RenderSongRequest) -> TaskInfo:
    task_id = str(uuid.uuid4())
    now = _utc_now()
    task = TaskInfo(
        task_id=task_id,
        status="queued",
        created_at=now,
        updated_at=now,
        message="Task queued",
    )
    with _task_lock:
        _tasks[task_id] = task

    executor.submit(_run_render_task, task_id, req)
    return task


@app.post("/v1/lodge/tasks/infer-and-render", response_model=TaskInfo)
def create_infer_and_render_task(req: InferAndRenderRequest) -> TaskInfo:
    task_id = str(uuid.uuid4())
    now = _utc_now()
    task = TaskInfo(
        task_id=task_id,
        status="queued",
        created_at=now,
        updated_at=now,
        message="Task queued",
    )
    with _task_lock:
        _tasks[task_id] = task

    executor.submit(_run_infer_and_render_task, task_id, req)
    return task


@app.get("/v1/lodge/tasks/{task_id}", response_model=TaskInfo)
def get_task(task_id: str) -> TaskInfo:
    with _task_lock:
        task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/v1/lodge/tasks/{task_id}/download")
def download_task_result(task_id: str) -> FileResponse:
    with _task_lock:
        task = _tasks.get(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "succeeded" or not task.output_mp4_path:
        raise HTTPException(status_code=409, detail="Task not completed")

    mp4_path = Path(task.output_mp4_path)
    if not mp4_path.exists():
        raise HTTPException(status_code=410, detail="Output file no longer exists")

    return FileResponse(
        path=str(mp4_path),
        media_type="video/mp4",
        filename=mp4_path.name,
    )
