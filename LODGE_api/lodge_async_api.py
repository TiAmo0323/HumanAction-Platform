import shutil
import subprocess
import sys
import threading
import uuid
import os
import json
import numpy as np
import uvicorn
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi import Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware


APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent
PLATFORM_ROOT = APP_ROOT.parent.parent
DEFAULT_TASK_ROOT = APP_ROOT / "task_runs"
DEFAULT_TASK_ROOT.mkdir(parents=True, exist_ok=True)
SUBPROCESS_ENCODING = os.getenv("LODGE_SUBPROCESS_ENCODING", "utf-8")
SUBPROCESS_ERRORS = os.getenv("LODGE_SUBPROCESS_ERRORS", "replace")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.skin_catalog import (
    SkinCatalogError,
    public_skin_catalog,
    resolve_skin_resource,
    resolve_skins,
    skin_requires_retarget,
)


def _default_target_fbx() -> str:
    return str((PLATFORM_ROOT / "X Bot.fbx").resolve())


def _default_mapping_file() -> str:
    return str((PLATFORM_ROOT / "momask-main" / "assets" / "mapping.json").resolve())


def _default_retarget_script() -> str:
    return str((APP_ROOT / "blender_rokoko_retarget.py").resolve())


class RenderSongRequest(BaseModel):
    lodge_root: str = Field(..., description="LODGE project root path, e.g. D:/LODGE-main")
    sample_dir: str = Field(..., description="Inference sample dir containing concat/npy, e.g. .../samples_dod_xxx")
    song_id: str = Field(..., description="Song id like 132")
    python_executable: Optional[str] = Field(default=sys.executable, description="Python executable in lodge conda env")
    mode: str = Field(default="smplx", pattern="^(smpl|smplh|smplx)$")
    device: str = Field(default="0", description="GPU device id string")
    fps: int = Field(default=30, ge=1, le=120)
    skin_ids: Optional[List[str]] = Field(
        default=None,
        description="One or more requested skin ids; takes precedence over legacy skin_id",
    )
    skin_id: Optional[str] = Field(
        default=None,
        description="Requested skin id from config/skin_catalog.json; defaults to smpl",
    )
    retarget_enabled: bool = Field(default=False, description="Export BVH and optionally run Blender/Rokoko retarget")
    target_fbx: Optional[str] = Field(default=None, description="Target character FBX path")
    mapping_file: Optional[str] = Field(default=None, description="Rokoko bone mapping JSON path")
    blender_executable: Optional[str] = Field(default=None, description="Blender executable path")
    retarget_script: Optional[str] = Field(default=None, description="Blender Python retarget script path")
    retarget_strict: bool = Field(default=False, description="Fail the task if retargeting fails")


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
    skin_ids: Optional[List[str]] = Field(
        default=None,
        description="One or more requested skin ids; takes precedence over legacy skin_id",
    )
    skin_id: Optional[str] = Field(
        default=None,
        description="Requested skin id from config/skin_catalog.json; defaults to smpl",
    )
    retarget_enabled: bool = Field(default=False, description="Export BVH and optionally run Blender/Rokoko retarget")
    target_fbx: Optional[str] = Field(default=None, description="Target character FBX path")
    mapping_file: Optional[str] = Field(default=None, description="Rokoko bone mapping JSON path")
    blender_executable: Optional[str] = Field(default=None, description="Blender executable path")
    retarget_script: Optional[str] = Field(default=None, description="Blender Python retarget script path")
    retarget_strict: bool = Field(default=False, description="Fail the task if retargeting fails")


class InferFromAudioRequest(BaseModel):
    lodge_root: str = Field(..., description="LODGE project root path, e.g. D:/LODGE-main")
    audio_path: str = Field(..., description="Local audio/video path (.wav/.mp3/.m4a/.mp4)")
    song_id: str = Field(..., description="Song id, recommend existing FineDance id like 132")
    python_executable: Optional[str] = Field(default=sys.executable, description="Python executable in lodge conda env")
    infer_args: List[str] = Field(
        default_factory=list,
        description="Extra args passed to infer_lodge.py, e.g. ['--soft', '1.0']",
    )
    mode: str = Field(default="smplx", pattern="^(smpl|smplh|smplx)$")
    device: str = Field(default="0", description="GPU device id string")
    fps: int = Field(default=30, ge=1, le=120)
    skin_ids: Optional[List[str]] = Field(
        default=None,
        description="One or more requested skin ids; takes precedence over legacy skin_id",
    )
    skin_id: Optional[str] = Field(
        default=None,
        description="Requested skin id from config/skin_catalog.json; defaults to smpl",
    )
    retarget_enabled: bool = Field(default=False, description="Export BVH and optionally run Blender/Rokoko retarget")
    target_fbx: Optional[str] = Field(default=None, description="Target character FBX path")
    mapping_file: Optional[str] = Field(default=None, description="Rokoko bone mapping JSON path")
    blender_executable: Optional[str] = Field(default=None, description="Blender executable path")
    retarget_script: Optional[str] = Field(default=None, description="Blender Python retarget script path")
    retarget_strict: bool = Field(default=False, description="Fail the task if retargeting fails")


class InferFromFeatureNpyRequest(BaseModel):
    lodge_root: str = Field(..., description="LODGE project root path, e.g. D:/LODGE-main")
    feature_npy_path: str = Field(..., description="Local audio-feature npy path")
    song_id: str = Field(..., description="Song id used as feature file stem")
    python_executable: Optional[str] = Field(default=sys.executable, description="Python executable in lodge conda env")
    infer_args: List[str] = Field(
        default_factory=list,
        description="Extra args passed to infer_lodge.py, e.g. ['--soft', '1.0']",
    )
    mode: str = Field(default="smplx", pattern="^(smpl|smplh|smplx)$")
    device: str = Field(default="0", description="GPU device id string")
    fps: int = Field(default=30, ge=1, le=120)
    skin_ids: Optional[List[str]] = Field(
        default=None,
        description="One or more requested skin ids; takes precedence over legacy skin_id",
    )
    skin_id: Optional[str] = Field(
        default=None,
        description="Requested skin id from config/skin_catalog.json; defaults to smpl",
    )
    retarget_enabled: bool = Field(default=False, description="Export BVH and optionally run Blender/Rokoko retarget")
    target_fbx: Optional[str] = Field(default=None, description="Target character FBX path")
    mapping_file: Optional[str] = Field(default=None, description="Rokoko bone mapping JSON path")
    blender_executable: Optional[str] = Field(default=None, description="Blender executable path")
    retarget_script: Optional[str] = Field(default=None, description="Blender Python retarget script path")
    retarget_strict: bool = Field(default=False, description="Fail the task if retargeting fails")


class TaskInfo(BaseModel):
    task_id: str
    status: str
    progress: int = Field(default=0, ge=0, le=100)
    created_at: str
    updated_at: str
    skin_id: str = "smpl"
    requested_skin_ids: List[str] = Field(default_factory=lambda: ["smpl"])
    available_skin_ids: List[str] = Field(default_factory=list)
    message: str = ""
    output_mp4_path: Optional[str] = None
    output_npy_path: Optional[str] = None
    output_bvh_path: Optional[str] = None
    output_retarget_mp4_path: Optional[str] = None
    output_retarget_path: Optional[str] = None
    retarget_status: str = ""
    retarget_message: str = ""
    stdout_tail: str = ""
    stderr_tail: str = ""


app = FastAPI(title="LODGE Async API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_tasks: Dict[str, TaskInfo] = {}
_task_lock = threading.Lock()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


executor = ThreadPoolExecutor(max_workers=max(1, _env_int("LODGE_MAX_CONCURRENT_TASKS", 1)))


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _tail_text(text: str, max_chars: int = 6000) -> str:
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _last_nonempty_line(text: str) -> str:
    for line in reversed((text or "").splitlines()):
        clean = line.strip()
        if clean:
            return clean
    return ""


def _resolve_request_skins(req) -> List[Dict[str, object]]:
    return resolve_skins(
        PROJECT_ROOT,
        getattr(req, "skin_ids", None),
        skin_id=getattr(req, "skin_id", None),
        legacy_retarget_enabled=bool(getattr(req, "retarget_enabled", False)),
    )


def _resolve_request_skin(req) -> Dict[str, object]:
    return _resolve_request_skins(req)[0]


def _validate_skin_selection(
    skin_ids: Optional[List[str]],
    skin_id: Optional[str] = None,
    retarget_enabled: bool = False,
) -> List[Dict[str, object]]:
    try:
        return resolve_skins(
            PROJECT_ROOT,
            skin_ids,
            skin_id=skin_id,
            legacy_retarget_enabled=retarget_enabled,
        )
    except SkinCatalogError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _validate_request_skins(req) -> List[Dict[str, object]]:
    return _validate_skin_selection(
        getattr(req, "skin_ids", None),
        getattr(req, "skin_id", None),
        bool(getattr(req, "retarget_enabled", False)),
    )


def _validate_request_skin(req) -> Dict[str, object]:
    return _validate_request_skins(req)[0]


def _update_task(task_id: str, **kwargs) -> None:
    with _task_lock:
        task = _tasks.get(task_id)
        if task is None:
            return
        if hasattr(task, "model_dump"):
            data = task.model_dump()
        else:
            data = task.dict()
        data.update(kwargs)
        retarget_path = data.get("output_retarget_mp4_path") or data.get("output_retarget_path")
        if retarget_path:
            data["output_retarget_mp4_path"] = retarget_path
            data["output_retarget_path"] = retarget_path
        available_skin_ids = []
        if data.get("output_mp4_path"):
            available_skin_ids.append("smpl")
        if data.get("retarget_status") == "succeeded" and retarget_path:
            requested_skin_ids = list(data.get("requested_skin_ids") or [])
            retarget_skin_id = next(
                (skin_id for skin_id in requested_skin_ids if skin_id != "smpl"),
                "robot",
            )
            available_skin_ids.append(retarget_skin_id)
        data["available_skin_ids"] = available_skin_ids
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
        encoding=SUBPROCESS_ENCODING,
        errors=SUBPROCESS_ERRORS,
        check=False,
    )


def _run_command_with_heartbeat(
    command: List[str],
    cwd: Path,
    task_id: str,
    running_message: str,
    progress: int,
    timeout_sec: Optional[int] = None,
    heartbeat_sec: int = 15,
    env_overrides: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    _update_task(task_id, message=running_message, progress=progress)
    env = os.environ.copy()
    if env_overrides:
        env.update({k: str(v) for k, v in env_overrides.items()})

    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding=SUBPROCESS_ENCODING,
        errors=SUBPROCESS_ERRORS,
        env=env,
    )

    start_ts = datetime.utcnow().timestamp()
    while True:
        elapsed = int(datetime.utcnow().timestamp() - start_ts)
        if timeout_sec is not None and elapsed >= timeout_sec:
            process.kill()
            stdout, stderr = process.communicate()
            stderr = (stderr or "") + f"\nProcess timeout after {timeout_sec} seconds"
            return subprocess.CompletedProcess(command, 124, stdout or "", stderr)

        try:
            stdout, stderr = process.communicate(timeout=heartbeat_sec)
            return subprocess.CompletedProcess(command, process.returncode or 0, stdout or "", stderr or "")
        except subprocess.TimeoutExpired:
            _update_task(
                task_id,
                message=f"{running_message} ({elapsed}s elapsed)",
                progress=progress,
            )


def _run_command_inherit_cwd(command: List[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding=SUBPROCESS_ENCODING,
        errors=SUBPROCESS_ERRORS,
        check=False,
    )


def _cap_motion_frames_inplace(npy_path: Path, max_frames: int) -> Optional[str]:
    if max_frames <= 0:
        return None

    try:
        data = np.load(str(npy_path), allow_pickle=False)
    except Exception:
        # Best effort: if shape cannot be parsed, skip truncation instead of failing the whole task.
        return None

    if getattr(data, "ndim", 0) < 1:
        return None

    frame_count = int(data.shape[0])
    if frame_count <= max_frames:
        return None

    np.save(str(npy_path), data[:max_frames])
    return f"Frame count clipped from {frame_count} to {max_frames}"


def _retarget_options_from_req(req) -> Dict[str, object]:
    skin_profiles = _resolve_request_skins(req)
    skin_profile = next(
        (profile for profile in skin_profiles if skin_requires_retarget(profile)),
        None,
    )
    render_smpl = any(
        str(profile.get("output_kind") or "") == "smpl"
        for profile in skin_profiles
    )
    return {
        "enabled": skin_profile is not None,
        "render_smpl": render_smpl,
        "skin_id": str(skin_profile["id"]) if skin_profile else "",
        "target_fbx": (
            getattr(req, "target_fbx", None)
            or (
                resolve_skin_resource(PROJECT_ROOT, skin_profile, "target_fbx")
                if skin_profile
                else None
            )
        ),
        "mapping_file": (
            getattr(req, "mapping_file", None)
            or (
                resolve_skin_resource(PROJECT_ROOT, skin_profile, "mapping_file")
                if skin_profile
                else None
            )
        ),
        "blender_executable": getattr(req, "blender_executable", None),
        "retarget_script": getattr(req, "retarget_script", None),
        "strict": bool(getattr(req, "retarget_strict", False)),
    }


def _export_bvh_for_npy(
    task_id: str,
    lodge_root: Path,
    target_npy: Path,
    python_exe: str,
    fps: int,
) -> Path:
    target_bvh = target_npy.with_suffix(".bvh")
    command = [
        python_exe,
        "lodge2bvh.py",
        "--input",
        str(target_npy),
        "--output",
        str(target_bvh),
        "--fps",
        str(fps),
    ]
    _update_task(task_id, progress=76, message="Exporting BVH from generated npy")
    proc = _run_command(command, lodge_root)
    if proc.returncode != 0 or not target_bvh.exists():
        raise RuntimeError(f"BVH export failed: {proc.stderr or proc.stdout}")
    _update_task(task_id, output_bvh_path=str(target_bvh.resolve()))
    return target_bvh


def _resolve_retarget_path(raw_value: Optional[str], env_name: str, default_value: str) -> Optional[Path]:
    raw = (raw_value or os.getenv(env_name, "") or default_value).strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def _run_retarget_if_requested(
    task_id: str,
    task_root: Path,
    source_npy: Path,
    source_bvh: Path,
    song_id: str,
    fps: int,
    retarget_options: Optional[Dict[str, object]],
) -> None:
    options = retarget_options or {}
    enabled = bool(options.get("enabled"))
    if not enabled:
        _update_task(task_id, retarget_status="skipped", retarget_message="Retarget disabled")
        return

    strict = bool(options.get("strict")) or _env_flag("LODGE_RETARGET_STRICT", False)
    retarget_dir = task_root / "retarget"
    retarget_dir.mkdir(parents=True, exist_ok=True)

    blender_exe = _resolve_retarget_path(
        options.get("blender_executable") if isinstance(options.get("blender_executable"), str) else None,
        "LODGE_BLENDER_EXE",
        "",
    )
    retarget_script = _resolve_retarget_path(
        options.get("retarget_script") if isinstance(options.get("retarget_script"), str) else None,
        "LODGE_RETARGET_SCRIPT",
        _default_retarget_script(),
    )
    target_fbx = _resolve_retarget_path(
        options.get("target_fbx") if isinstance(options.get("target_fbx"), str) else None,
        "LODGE_TARGET_FBX",
        _default_target_fbx(),
    )
    mapping_file = _resolve_retarget_path(
        options.get("mapping_file") if isinstance(options.get("mapping_file"), str) else None,
        "LODGE_RETARGET_MAPPING",
        _default_mapping_file(),
    )

    output_mp4 = retarget_dir / f"{song_id}_retarget.mp4"
    report_path = retarget_dir / "rokoko_retarget_report.json"
    manifest_path = retarget_dir / "retarget_manifest.json"

    manifest = {
        "task_id": task_id,
        "skin_id": str(options.get("skin_id") or "robot"),
        "engine": "blender-rokoko",
        "source_npy": str(source_npy.resolve()),
        "source_bvh": str(source_bvh.resolve()),
        "source_bvh_files": [str(source_bvh.resolve())],
        "target_fbx": str(target_fbx),
        "mapping_file": str(mapping_file),
        "output_mp4": str(output_mp4.resolve()),
        "report_path": str(report_path.resolve()),
        "debug_blend": str((retarget_dir / "retarget_debug.blend").resolve()),
        "fps": fps,
        "max_render_frames": _env_int("LODGE_RETARGET_MAX_RENDER_FRAMES", 120),
        "render_size": os.getenv("LODGE_RETARGET_RENDER_SIZE", "1080x1080"),
        "render_engine": os.getenv(
            "LODGE_RETARGET_RENDER_ENGINE",
            "BLENDER_EEVEE_NEXT",
        ),
        "eevee_render_samples": _env_int("LODGE_RETARGET_EEVEE_SAMPLES", 32),
        "resolution_percentage": _env_int(
            "LODGE_RETARGET_RESOLUTION_PERCENTAGE",
            100,
        ),
        "camera_distance_scale": _env_float("LODGE_RETARGET_CAMERA_DISTANCE_SCALE", 1.15),
        "hand_torso_collision_enabled": _env_flag(
            "LODGE_RETARGET_HAND_TORSO_COLLISION",
            True,
        ),
        "hand_torso_collision_torso_minimum_weight": _env_float(
            "LODGE_RETARGET_HAND_TORSO_MINIMUM_WEIGHT",
            0.5,
        ),
        "hand_torso_collision_slice_half_height": _env_float(
            "LODGE_RETARGET_HAND_TORSO_SLICE_HALF_HEIGHT",
            0.05,
        ),
        "hand_torso_collision_proxy_scale": _env_float(
            "LODGE_RETARGET_HAND_TORSO_PROXY_SCALE",
            0.95,
        ),
        "hand_torso_collision_clearance": _env_float(
            "LODGE_RETARGET_HAND_TORSO_CLEARANCE",
            0.025,
        ),
        "hand_torso_collision_penetration_threshold": _env_float(
            "LODGE_RETARGET_HAND_TORSO_PENETRATION_THRESHOLD",
            0.005,
        ),
        "hand_torso_collision_blend_frames": _env_int(
            "LODGE_RETARGET_HAND_TORSO_BLEND_FRAMES",
            4,
        ),
        "hand_torso_collision_smoothing_window": _env_int(
            "LODGE_RETARGET_HAND_TORSO_SMOOTHING_WINDOW",
            5,
        ),
        "hand_torso_collision_max_correction": _env_float(
            "LODGE_RETARGET_HAND_TORSO_MAX_CORRECTION",
            0.12,
        ),
        "created_at": _utc_now(),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    required_paths = [blender_exe, retarget_script, target_fbx, mapping_file, source_bvh]
    missing = [str(path) if path is not None else "(empty)" for path in required_paths if path is None or not path.exists()]
    if missing:
        message = "Retarget skipped, missing required path(s): " + "; ".join(missing)
        _update_task(task_id, retarget_status="skipped", retarget_message=message)
        if strict:
            raise FileNotFoundError(message)
        return

    command = [
        str(blender_exe),
        "--background",
        "--python",
        str(retarget_script),
        "--",
        "--manifest",
        str(manifest_path),
    ]
    _update_task(task_id, progress=78, message="Running Blender/Rokoko retarget", retarget_status="running")
    timeout_sec = _env_int("LODGE_RETARGET_TIMEOUT_SEC", 3600)
    proc = _run_command_with_heartbeat(
        command=command,
        cwd=retarget_dir,
        task_id=task_id,
        running_message="Running Blender/Rokoko retarget",
        progress=78,
        timeout_sec=timeout_sec,
        heartbeat_sec=10,
    )
    if proc.returncode == 0 and output_mp4.exists():
        _update_task(
            task_id,
            output_retarget_mp4_path=str(output_mp4.resolve()),
            retarget_status="succeeded",
            retarget_message="Rokoko retarget completed",
        )
        return

    message = _last_nonempty_line(proc.stderr) or _last_nonempty_line(proc.stdout) or "Blender/Rokoko retarget failed"
    _update_task(
        task_id,
        retarget_status="failed",
        retarget_message=message,
        stderr_tail=_tail_text(proc.stderr or ""),
        stdout_tail=_tail_text(proc.stdout or ""),
    )
    if strict:
        raise RuntimeError(message)


def _build_render_attempts(mode: str, fps: int) -> List[Tuple[str, int]]:
    attempts: List[Tuple[str, int]] = [(mode, fps)]
    if not _env_flag("LODGE_RENDER_RETRY_ENABLED", True):
        return attempts

    fallback_mode = os.getenv("LODGE_RENDER_FALLBACK_MODE", "smpl").strip() or "smpl"
    fallback_fps = _env_int("LODGE_RENDER_FALLBACK_FPS", min(fps, 24))
    fallback = (fallback_mode, fallback_fps)
    if fallback not in attempts:
        attempts.append(fallback)
    return attempts


def _render_with_retry(
    task_id: str,
    lodge_root: Path,
    input_dir: Path,
    song_id: str,
    python_exe: str,
    mode: str,
    device: str,
    fps: int,
) -> None:
    render_timeout_sec = _env_int("LODGE_RENDER_TIMEOUT_SEC", 3600)
    attempts = _build_render_attempts(mode=mode, fps=fps)
    stdout_blocks: List[str] = []
    stderr_blocks: List[str] = []

    for idx, (attempt_mode, attempt_fps) in enumerate(attempts, start=1):
        render_command = [
            python_exe,
            "render.py",
            "--modir",
            str(input_dir),
            "--mode",
            attempt_mode,
            "--device",
            device,
            "--fps",
            str(attempt_fps),
        ]

        progress = 80 if idx == 1 else 88
        running_message = f"Rendering mp4 (attempt {idx}/{len(attempts)}, mode={attempt_mode}, fps={attempt_fps})"
        proc = _run_command_with_heartbeat(
            command=render_command,
            cwd=lodge_root,
            task_id=task_id,
            running_message=running_message,
            progress=progress,
            timeout_sec=render_timeout_sec,
            heartbeat_sec=10,
        )

        stdout_blocks.append(f"[attempt {idx}]\n{proc.stdout or ''}")
        stderr_blocks.append(f"[attempt {idx}]\n{proc.stderr or ''}")

        if proc.returncode == 0:
            video_dir = input_dir / "video"
            output_mp4 = _find_rendered_mp4(video_dir, song_id)
            _update_task(
                task_id,
                status="succeeded",
                progress=100,
                message="Task completed",
                output_mp4_path=str(output_mp4.resolve()),
                stdout_tail=_tail_text("\n\n".join(stdout_blocks)),
                stderr_tail=_tail_text("\n\n".join(stderr_blocks)),
            )
            return

        if idx < len(attempts):
            _update_task(task_id, message="Render attempt failed, retrying with fallback settings", progress=86)

    _update_task(
        task_id,
        status="failed",
        message="render.py failed after fallback retry",
        stdout_tail=_tail_text("\n\n".join(stdout_blocks)),
        stderr_tail=_tail_text("\n\n".join(stderr_blocks)),
    )


def _resolve_music_npy_dir(lodge_root: Path) -> Path:
    candidates = [
        lodge_root / "data" / "finedance" / "music_npy",
        lodge_root / "data" / "finedance" / "music_npynew",
        lodge_root / "data" / "finedance" / "music_npynew" / "music_npy_new",
    ]
    for c in candidates:
        if c.exists():
            return c
    candidates[0].mkdir(parents=True, exist_ok=True)
    return candidates[0]


def _detect_latest_sample_dir_after(lodge_root: Path, min_mtime: float) -> Path:
    experiments_root = lodge_root / "experiments"
    if not experiments_root.exists():
        raise FileNotFoundError(f"experiments dir not found: {experiments_root}")

    candidates = [
        p
        for p in experiments_root.rglob("samples_dod_*")
        if p.is_dir() and (p / "concat" / "npy").exists() and p.stat().st_mtime >= min_mtime
    ]
    if not candidates:
        raise FileNotFoundError("No new samples_dod_* dir generated after infer started")

    candidates.sort(key=lambda p: p.stat().st_mtime)
    return candidates[-1]


def _normalize_song_id(song_id: str) -> str:
    clean = (song_id or "").strip()
    if not clean:
        raise ValueError("song_id is empty")
    return clean


def _ensure_wav_source(task_root: Path, source_audio: Path, lodge_root: Path) -> Path:
    input_dir = task_root / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    suffix = source_audio.suffix.lower()
    if suffix == ".wav":
        dst = input_dir / "input.wav"
        shutil.copy2(source_audio, dst)
        return dst

    if suffix in {".mp4", ".m4a", ".mp3", ".aac", ".flac", ".ogg"}:
        dst = input_dir / "input.wav"
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(source_audio),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "15360",
            str(dst),
        ]
        proc = _run_command_inherit_cwd(ffmpeg_cmd, lodge_root)
        if proc.returncode != 0 or not dst.exists():
            raise RuntimeError(f"ffmpeg convert failed: {proc.stderr or proc.stdout}")
        return dst

    raise ValueError(f"Unsupported audio format: {source_audio.suffix}")


def _extract_music_feature_npy(lodge_root: Path, python_exe: str, wav_path: Path, out_npy: Path) -> subprocess.CompletedProcess:
    code = (
        "import numpy as np; "
        "from dld.data.utils.audio import extract; "
        f"fea,_=extract(r'{str(wav_path)}'); "
        f"np.save(r'{str(out_npy)}', fea)"
    )
    return _run_command_inherit_cwd([python_exe, "-c", code], lodge_root)


def _finalize_retarget_only_task(task_id: str) -> None:
    with _task_lock:
        current = _tasks.get(task_id)
    retarget_succeeded = bool(
        current
        and current.retarget_status == "succeeded"
        and (current.output_retarget_mp4_path or current.output_retarget_path)
    )
    if retarget_succeeded:
        _update_task(
            task_id,
            status="succeeded",
            progress=100,
            message="Requested retarget skin completed",
            output_mp4_path=None,
        )
        return
    reason = current.retarget_message if current else "Retarget state unavailable"
    _update_task(
        task_id,
        status="failed",
        progress=100,
        message=f"Requested retarget skin was not generated: {reason}",
        output_mp4_path=None,
    )


def _render_from_sample_dir(
    task_id: str,
    lodge_root: Path,
    sample_dir: Path,
    song_id: str,
    python_exe: str,
    mode: str,
    device: str,
    fps: int,
    retarget_options: Optional[Dict[str, object]] = None,
) -> None:
    source_npy = sample_dir / "concat" / "npy" / f"{song_id}.npy"
    if not source_npy.exists():
        raise FileNotFoundError(f"Source npy not found: {source_npy}")

    task_root = DEFAULT_TASK_ROOT / task_id
    input_dir = task_root / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    target_npy = input_dir / f"{song_id}.npy"
    shutil.copy2(source_npy, target_npy)
    _update_task(task_id, output_npy_path=str(target_npy.resolve()))
    clip_note = _cap_motion_frames_inplace(target_npy, _env_int("LODGE_MAX_RENDER_FRAMES", 2000))
    if clip_note:
        _update_task(task_id, message=clip_note, progress=75)

    target_bvh = _export_bvh_for_npy(
        task_id=task_id,
        lodge_root=lodge_root,
        target_npy=target_npy,
        python_exe=python_exe,
        fps=fps,
    )
    task_root = DEFAULT_TASK_ROOT / task_id
    _run_retarget_if_requested(
        task_id=task_id,
        task_root=task_root,
        source_npy=target_npy,
        source_bvh=target_bvh,
        song_id=song_id,
        fps=fps,
        retarget_options=retarget_options,
    )

    if bool((retarget_options or {}).get("render_smpl", True)):
        _render_with_retry(
            task_id=task_id,
            lodge_root=lodge_root,
            input_dir=input_dir,
            song_id=song_id,
            python_exe=python_exe,
            mode=mode,
            device=device,
            fps=fps,
        )
    else:
        _finalize_retarget_only_task(task_id)


def _render_from_npy_file(
    task_id: str,
    lodge_root: Path,
    source_npy: Path,
    song_id: str,
    python_exe: str,
    mode: str,
    device: str,
    fps: int,
    retarget_options: Optional[Dict[str, object]] = None,
) -> None:
    if not source_npy.exists():
        raise FileNotFoundError(f"Source npy not found: {source_npy}")

    task_root = DEFAULT_TASK_ROOT / task_id
    input_dir = task_root / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    target_npy = input_dir / f"{song_id}.npy"
    shutil.copy2(source_npy, target_npy)
    _update_task(task_id, output_npy_path=str(target_npy.resolve()))
    clip_note = _cap_motion_frames_inplace(target_npy, _env_int("LODGE_MAX_RENDER_FRAMES", 2000))
    if clip_note:
        _update_task(task_id, message=clip_note, progress=75)

    target_bvh = _export_bvh_for_npy(
        task_id=task_id,
        lodge_root=lodge_root,
        target_npy=target_npy,
        python_exe=python_exe,
        fps=fps,
    )
    task_root = DEFAULT_TASK_ROOT / task_id
    _run_retarget_if_requested(
        task_id=task_id,
        task_root=task_root,
        source_npy=target_npy,
        source_bvh=target_bvh,
        song_id=song_id,
        fps=fps,
        retarget_options=retarget_options,
    )

    if bool((retarget_options or {}).get("render_smpl", True)):
        _render_with_retry(
            task_id=task_id,
            lodge_root=lodge_root,
            input_dir=input_dir,
            song_id=song_id,
            python_exe=python_exe,
            mode=mode,
            device=device,
            fps=fps,
        )
    else:
        _finalize_retarget_only_task(task_id)


def _run_render_task(task_id: str, req: RenderSongRequest) -> None:
    try:
        _update_task(task_id, status="running", progress=10, message="Task is running")

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
            retarget_options=_retarget_options_from_req(req),
        )

    except Exception as exc:
        _update_task(task_id, status="failed", message=str(exc))


def _run_infer_and_render_task(task_id: str, req: InferAndRenderRequest) -> None:
    try:
        _update_task(task_id, status="running", progress=10, message="Running infer_lodge.py")

        lodge_root = Path(req.lodge_root).resolve()
        if not lodge_root.exists():
            raise FileNotFoundError(f"lodge_root not found: {lodge_root}")

        infer_timeout_sec = int(os.getenv("LODGE_INFER_TIMEOUT_SEC", "3600"))
        infer_command = [req.python_executable or sys.executable, "infer_lodge.py"] + req.infer_args
        infer_proc = _run_command_with_heartbeat(
            command=infer_command,
            cwd=lodge_root,
            task_id=task_id,
            running_message="Running infer_lodge.py",
            progress=45,
            timeout_sec=infer_timeout_sec,
            env_overrides={"LODGE_SONG_IDS": req.song_id},
        )
        infer_stdout = _tail_text(infer_proc.stdout or "")
        infer_stderr = _tail_text(infer_proc.stderr or "")

        if infer_proc.returncode != 0:
            reason = _last_nonempty_line(infer_stderr) or _last_nonempty_line(infer_stdout)
            msg = f"infer_lodge.py failed with return code {infer_proc.returncode}"
            if reason:
                msg = f"{msg}: {reason}"
            _update_task(
                task_id,
                status="failed",
                message=msg,
                stdout_tail=infer_stdout,
                stderr_tail=infer_stderr,
            )
            return

        _update_task(task_id, progress=65, message="Inference done, rendering mp4")

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
            retarget_options=_retarget_options_from_req(req),
        )

    except Exception as exc:
        _update_task(task_id, status="failed", message=str(exc))


def _run_infer_from_audio_task(task_id: str, req: InferFromAudioRequest) -> None:
    try:
        _update_task(task_id, status="running", progress=10, message="Preparing audio features")

        lodge_root = Path(req.lodge_root).resolve()
        audio_path = Path(req.audio_path).resolve()
        song_id = _normalize_song_id(req.song_id)

        if not lodge_root.exists():
            raise FileNotFoundError(f"lodge_root not found: {lodge_root}")
        if not audio_path.exists():
            raise FileNotFoundError(f"audio_path not found: {audio_path}")

        task_root = DEFAULT_TASK_ROOT / task_id
        wav_path = _ensure_wav_source(task_root, audio_path, lodge_root)

        music_npy_dir = _resolve_music_npy_dir(lodge_root)
        out_npy = music_npy_dir / f"{song_id}.npy"

        _update_task(task_id, progress=25, message="Extracting audio features to npy")
        fea_proc = _extract_music_feature_npy(
            lodge_root=lodge_root,
            python_exe=req.python_executable or sys.executable,
            wav_path=wav_path,
            out_npy=out_npy,
        )
        if fea_proc.returncode != 0 or not out_npy.exists():
            _update_task(
                task_id,
                status="failed",
                message="Feature extraction failed",
                stdout_tail=_tail_text(fea_proc.stdout or ""),
                stderr_tail=_tail_text(fea_proc.stderr or ""),
            )
            return

        _update_task(task_id, progress=45, message="Running infer_lodge.py")
        start_ts = datetime.utcnow().timestamp()
        infer_timeout_sec = int(os.getenv("LODGE_INFER_TIMEOUT_SEC", "3600"))
        infer_command = [req.python_executable or sys.executable, "infer_lodge.py"] + req.infer_args
        infer_proc = _run_command_with_heartbeat(
            command=infer_command,
            cwd=lodge_root,
            task_id=task_id,
            running_message="Running infer_lodge.py",
            progress=45,
            timeout_sec=infer_timeout_sec,
            env_overrides={
                "LODGE_FORCE_CACHED_FEATURES": "1",
                "LODGE_MUSIC_DIR": str(music_npy_dir),
                "LODGE_SONG_IDS": song_id,
            },
        )
        infer_stdout = _tail_text(infer_proc.stdout or "")
        infer_stderr = _tail_text(infer_proc.stderr or "")

        if infer_proc.returncode != 0:
            reason = _last_nonempty_line(infer_stderr) or _last_nonempty_line(infer_stdout)
            msg = f"infer_lodge.py failed with return code {infer_proc.returncode}"
            if reason:
                msg = f"{msg}: {reason}"
            _update_task(
                task_id,
                status="failed",
                message=msg,
                stdout_tail=infer_stdout,
                stderr_tail=infer_stderr,
            )
            return

        _update_task(task_id, progress=70, message="Inference done, rendering mp4")
        sample_dir = _detect_latest_sample_dir_after(lodge_root, start_ts)
        _render_from_sample_dir(
            task_id=task_id,
            lodge_root=lodge_root,
            sample_dir=sample_dir,
            song_id=song_id,
            python_exe=req.python_executable or sys.executable,
            mode=req.mode,
            device=req.device,
            fps=req.fps,
            retarget_options=_retarget_options_from_req(req),
        )

    except Exception as exc:
        _update_task(task_id, status="failed", message=str(exc))


def _run_infer_from_feature_npy_task(task_id: str, req: InferFromFeatureNpyRequest) -> None:
    try:
        _update_task(task_id, status="running", progress=10, message="Preparing feature npy")

        lodge_root = Path(req.lodge_root).resolve()
        feature_npy_path = Path(req.feature_npy_path).resolve()
        song_id = _normalize_song_id(req.song_id)

        if not lodge_root.exists():
            raise FileNotFoundError(f"lodge_root not found: {lodge_root}")
        if not feature_npy_path.exists():
            raise FileNotFoundError(f"feature_npy_path not found: {feature_npy_path}")

        music_npy_dir = _resolve_music_npy_dir(lodge_root)
        out_npy = music_npy_dir / f"{song_id}.npy"
        shutil.copy2(feature_npy_path, out_npy)

        _update_task(task_id, progress=45, message="Running infer_lodge.py")
        start_ts = datetime.utcnow().timestamp()
        infer_timeout_sec = int(os.getenv("LODGE_INFER_TIMEOUT_SEC", "3600"))
        infer_command = [req.python_executable or sys.executable, "infer_lodge.py"] + req.infer_args
        infer_proc = _run_command_with_heartbeat(
            command=infer_command,
            cwd=lodge_root,
            task_id=task_id,
            running_message="Running infer_lodge.py",
            progress=45,
            timeout_sec=infer_timeout_sec,
            env_overrides={
                "LODGE_FORCE_CACHED_FEATURES": "1",
                "LODGE_MUSIC_DIR": str(music_npy_dir),
                "LODGE_SONG_IDS": song_id,
            },
        )
        infer_stdout = _tail_text(infer_proc.stdout or "")
        infer_stderr = _tail_text(infer_proc.stderr or "")

        if infer_proc.returncode != 0:
            reason = _last_nonempty_line(infer_stderr) or _last_nonempty_line(infer_stdout)
            msg = f"infer_lodge.py failed with return code {infer_proc.returncode}"
            if reason:
                msg = f"{msg}: {reason}"
            _update_task(
                task_id,
                status="failed",
                message=msg,
                stdout_tail=infer_stdout,
                stderr_tail=infer_stderr,
            )
            return

        _update_task(task_id, progress=70, message="Inference done, rendering mp4")
        sample_dir = _detect_latest_sample_dir_after(lodge_root, start_ts)
        _render_from_sample_dir(
            task_id=task_id,
            lodge_root=lodge_root,
            sample_dir=sample_dir,
            song_id=song_id,
            python_exe=req.python_executable or sys.executable,
            mode=req.mode,
            device=req.device,
            fps=req.fps,
            retarget_options=_retarget_options_from_req(req),
        )

    except Exception as exc:
        _update_task(task_id, status="failed", message=str(exc))


def _run_render_from_uploaded_npy_task(
    task_id: str,
    lodge_root: str,
    uploaded_npy_path: str,
    song_id: str,
    python_executable: Optional[str],
    mode: str,
    device: str,
    fps: int,
    retarget_options: Optional[Dict[str, object]] = None,
) -> None:
    try:
        _update_task(task_id, status="running", progress=20, message="Rendering uploaded npy")

        root_path = Path(lodge_root).resolve()
        npy_path = Path(uploaded_npy_path).resolve()
        if not root_path.exists():
            raise FileNotFoundError(f"lodge_root not found: {root_path}")
        if not npy_path.exists():
            raise FileNotFoundError(f"uploaded npy not found: {npy_path}")

        _render_from_npy_file(
            task_id=task_id,
            lodge_root=root_path,
            source_npy=npy_path,
            song_id=song_id,
            python_exe=python_executable or sys.executable,
            mode=mode,
            device=device,
            fps=fps,
            retarget_options=retarget_options,
        )
    except Exception as exc:
        _update_task(task_id, status="failed", message=str(exc))


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/lodge/skins")
def get_supported_skins() -> Dict[str, object]:
    try:
        return public_skin_catalog(PROJECT_ROOT)
    except SkinCatalogError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/v1/lodge/tasks/render-song", response_model=TaskInfo)
def create_render_song_task(req: RenderSongRequest) -> TaskInfo:
    skin_profiles = _validate_request_skins(req)
    requested_skin_ids = [str(profile["id"]) for profile in skin_profiles]
    task_id = str(uuid.uuid4())
    now = _utc_now()
    task = TaskInfo(
        task_id=task_id,
        status="queued",
        progress=0,
        created_at=now,
        updated_at=now,
        skin_id=requested_skin_ids[0],
        requested_skin_ids=requested_skin_ids,
        message="Task queued",
    )
    with _task_lock:
        _tasks[task_id] = task

    executor.submit(_run_render_task, task_id, req)
    return task


@app.post("/v1/lodge/tasks/infer-and-render", response_model=TaskInfo)
def create_infer_and_render_task(req: InferAndRenderRequest) -> TaskInfo:
    skin_profiles = _validate_request_skins(req)
    requested_skin_ids = [str(profile["id"]) for profile in skin_profiles]
    task_id = str(uuid.uuid4())
    now = _utc_now()
    task = TaskInfo(
        task_id=task_id,
        status="queued",
        progress=0,
        created_at=now,
        updated_at=now,
        skin_id=requested_skin_ids[0],
        requested_skin_ids=requested_skin_ids,
        message="Task queued",
    )
    with _task_lock:
        _tasks[task_id] = task

    executor.submit(_run_infer_and_render_task, task_id, req)
    return task


@app.post("/v1/lodge/tasks/infer-from-audio", response_model=TaskInfo)
def create_infer_from_audio_task(req: InferFromAudioRequest) -> TaskInfo:
    skin_profiles = _validate_request_skins(req)
    requested_skin_ids = [str(profile["id"]) for profile in skin_profiles]
    task_id = str(uuid.uuid4())
    now = _utc_now()
    task = TaskInfo(
        task_id=task_id,
        status="queued",
        progress=0,
        created_at=now,
        updated_at=now,
        skin_id=requested_skin_ids[0],
        requested_skin_ids=requested_skin_ids,
        message="Task queued",
    )
    with _task_lock:
        _tasks[task_id] = task

    executor.submit(_run_infer_from_audio_task, task_id, req)
    return task


@app.post("/v1/lodge/tasks/infer-from-audio-upload", response_model=TaskInfo)
async def create_infer_from_audio_upload_task(
    lodge_root: str = Form(...),
    song_id: str = Form(...),
    audio_file: UploadFile = File(...),
    python_executable: Optional[str] = Form(default=None),
    mode: str = Form(default="smplx"),
    device: str = Form(default="0"),
    fps: int = Form(default=30),
    infer_args: str = Form(default=""),
    skin_ids: Optional[List[str]] = Form(default=None),
    skin_id: Optional[str] = Form(default=None),
    retarget_enabled: bool = Form(default=False),
    target_fbx: Optional[str] = Form(default=None),
    mapping_file: Optional[str] = Form(default=None),
    blender_executable: Optional[str] = Form(default=None),
    retarget_script: Optional[str] = Form(default=None),
    retarget_strict: bool = Form(default=False),
) -> TaskInfo:
    skin_profiles = _validate_skin_selection(skin_ids, skin_id, retarget_enabled)
    requested_skin_ids = [str(profile["id"]) for profile in skin_profiles]
    task_id = str(uuid.uuid4())
    now = _utc_now()
    task = TaskInfo(
        task_id=task_id,
        status="queued",
        progress=0,
        created_at=now,
        updated_at=now,
        skin_id=requested_skin_ids[0],
        requested_skin_ids=requested_skin_ids,
        message="Task queued",
    )
    with _task_lock:
        _tasks[task_id] = task

    task_root = DEFAULT_TASK_ROOT / task_id
    input_dir = task_root / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(audio_file.filename or "upload.wav").suffix or ".wav"
    saved_path = input_dir / f"uploaded{suffix}"
    content = await audio_file.read()
    saved_path.write_bytes(content)

    args = [x.strip() for x in infer_args.split(",") if x.strip()] if infer_args else []
    req = InferFromAudioRequest(
        lodge_root=lodge_root,
        audio_path=str(saved_path),
        song_id=song_id,
        python_executable=python_executable or sys.executable,
        infer_args=args,
        mode=mode,
        device=device,
        fps=fps,
        skin_ids=requested_skin_ids,
        skin_id=requested_skin_ids[0],
        retarget_enabled=retarget_enabled,
        target_fbx=target_fbx,
        mapping_file=mapping_file,
        blender_executable=blender_executable,
        retarget_script=retarget_script,
        retarget_strict=retarget_strict,
    )

    executor.submit(_run_infer_from_audio_task, task_id, req)
    return task


@app.post("/v1/lodge/tasks/render-from-npy-upload", response_model=TaskInfo)
async def create_render_from_npy_upload_task(
    lodge_root: str = Form(...),
    song_id: str = Form(...),
    npy_file: UploadFile = File(...),
    python_executable: Optional[str] = Form(default=None),
    mode: str = Form(default="smplx"),
    device: str = Form(default="0"),
    fps: int = Form(default=30),
    skin_ids: Optional[List[str]] = Form(default=None),
    skin_id: Optional[str] = Form(default=None),
    retarget_enabled: bool = Form(default=False),
    target_fbx: Optional[str] = Form(default=None),
    mapping_file: Optional[str] = Form(default=None),
    blender_executable: Optional[str] = Form(default=None),
    retarget_script: Optional[str] = Form(default=None),
    retarget_strict: bool = Form(default=False),
) -> TaskInfo:
    skin_profiles = _validate_skin_selection(skin_ids, skin_id, retarget_enabled)
    requested_skin_ids = [str(profile["id"]) for profile in skin_profiles]
    retarget_profile = next(
        (profile for profile in skin_profiles if skin_requires_retarget(profile)),
        None,
    )
    render_smpl = any(
        str(profile.get("output_kind") or "") == "smpl"
        for profile in skin_profiles
    )
    task_id = str(uuid.uuid4())
    now = _utc_now()
    task = TaskInfo(
        task_id=task_id,
        status="queued",
        progress=0,
        created_at=now,
        updated_at=now,
        skin_id=requested_skin_ids[0],
        requested_skin_ids=requested_skin_ids,
        message="Task queued",
    )
    with _task_lock:
        _tasks[task_id] = task

    task_root = DEFAULT_TASK_ROOT / task_id
    input_dir = task_root / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    saved_path = input_dir / "uploaded.npy"
    saved_path.write_bytes(await npy_file.read())

    executor.submit(
        _run_render_from_uploaded_npy_task,
        task_id,
        lodge_root,
        str(saved_path),
        song_id,
        python_executable,
        mode,
        device,
        fps,
        {
            "enabled": retarget_profile is not None,
            "render_smpl": render_smpl,
            "skin_id": str(retarget_profile["id"]) if retarget_profile else "",
            "target_fbx": (
                target_fbx
                or (
                    resolve_skin_resource(PROJECT_ROOT, retarget_profile, "target_fbx")
                    if retarget_profile
                    else None
                )
            ),
            "mapping_file": (
                mapping_file
                or (
                    resolve_skin_resource(PROJECT_ROOT, retarget_profile, "mapping_file")
                    if retarget_profile
                    else None
                )
            ),
            "blender_executable": blender_executable,
            "retarget_script": retarget_script,
            "strict": retarget_strict,
        },
    )
    return task


@app.post("/v1/lodge/tasks/infer-from-feature-npy-upload", response_model=TaskInfo)
async def create_infer_from_feature_npy_upload_task(
    lodge_root: str = Form(...),
    song_id: str = Form(...),
    npy_file: UploadFile = File(...),
    python_executable: Optional[str] = Form(default=None),
    mode: str = Form(default="smplx"),
    device: str = Form(default="0"),
    fps: int = Form(default=30),
    infer_args: str = Form(default=""),
    skin_ids: Optional[List[str]] = Form(default=None),
    skin_id: Optional[str] = Form(default=None),
    retarget_enabled: bool = Form(default=False),
    target_fbx: Optional[str] = Form(default=None),
    mapping_file: Optional[str] = Form(default=None),
    blender_executable: Optional[str] = Form(default=None),
    retarget_script: Optional[str] = Form(default=None),
    retarget_strict: bool = Form(default=False),
) -> TaskInfo:
    skin_profiles = _validate_skin_selection(skin_ids, skin_id, retarget_enabled)
    requested_skin_ids = [str(profile["id"]) for profile in skin_profiles]
    task_id = str(uuid.uuid4())
    now = _utc_now()
    task = TaskInfo(
        task_id=task_id,
        status="queued",
        progress=0,
        created_at=now,
        updated_at=now,
        skin_id=requested_skin_ids[0],
        requested_skin_ids=requested_skin_ids,
        message="Task queued",
    )
    with _task_lock:
        _tasks[task_id] = task

    task_root = DEFAULT_TASK_ROOT / task_id
    input_dir = task_root / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    saved_path = input_dir / "uploaded_feature.npy"
    saved_path.write_bytes(await npy_file.read())

    args = [x.strip() for x in infer_args.split(",") if x.strip()] if infer_args else []
    req = InferFromFeatureNpyRequest(
        lodge_root=lodge_root,
        feature_npy_path=str(saved_path),
        song_id=song_id,
        python_executable=python_executable or sys.executable,
        infer_args=args,
        mode=mode,
        device=device,
        fps=fps,
        skin_ids=requested_skin_ids,
        skin_id=requested_skin_ids[0],
        retarget_enabled=retarget_enabled,
        target_fbx=target_fbx,
        mapping_file=mapping_file,
        blender_executable=blender_executable,
        retarget_script=retarget_script,
        retarget_strict=retarget_strict,
    )

    executor.submit(_run_infer_from_feature_npy_task, task_id, req)
    return task


@app.get("/v1/lodge/tasks/{task_id}", response_model=TaskInfo)
def get_task(task_id: str) -> TaskInfo:
    with _task_lock:
        task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _selected_task_video_path(task: TaskInfo, skin_id: Optional[str]) -> Path:
    selected_skin_id = (skin_id or task.skin_id or "smpl").strip()
    if selected_skin_id != "smpl":
        retarget_path = task.output_retarget_mp4_path or task.output_retarget_path
        if task.retarget_status != "succeeded" or not retarget_path:
            raise HTTPException(status_code=409, detail="Selected skin result not completed")
        return Path(retarget_path)
    if task.status != "succeeded" or not task.output_mp4_path:
        raise HTTPException(status_code=409, detail="Task not completed")
    return Path(task.output_mp4_path)


@app.post("/v1/lodge/tasks/{task_id}/open-output-folder")
def open_task_output_folder(task_id: str, skin_id: Optional[str] = None) -> Dict[str, str]:
    with _task_lock:
        task = _tasks.get(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    mp4_path = _selected_task_video_path(task, skin_id)
    if not mp4_path.exists():
        raise HTTPException(status_code=410, detail="Output file no longer exists")

    parent_dir = mp4_path.parent
    try:
        if os.name == "nt":
            subprocess.Popen(["explorer", f"/select,{str(mp4_path)}"])  # nosec B603
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(parent_dir)])  # nosec B603
        else:
            subprocess.Popen(["xdg-open", str(parent_dir)])  # nosec B603
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to open folder: {exc}")

    return {"status": "ok", "opened_path": str(parent_dir)}


@app.post("/v1/lodge/tasks/{task_id}/open-output-player")
def open_task_output_player(task_id: str, skin_id: Optional[str] = None) -> Dict[str, str]:
    with _task_lock:
        task = _tasks.get(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    mp4_path = _selected_task_video_path(task, skin_id)
    if not mp4_path.exists():
        raise HTTPException(status_code=410, detail="Output file no longer exists")

    try:
        if os.name == "nt":
            os.startfile(str(mp4_path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(mp4_path)])  # nosec B603
        else:
            subprocess.Popen(["xdg-open", str(mp4_path)])  # nosec B603
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to open player: {exc}")

    return {"status": "ok", "opened_file": str(mp4_path)}


@app.get("/v1/lodge/tasks/{task_id}/download")
def download_task_result(task_id: str, request: Request, as_attachment: bool = False):
    with _task_lock:
        task = _tasks.get(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "succeeded" or not task.output_mp4_path:
        raise HTTPException(status_code=409, detail="Task not completed")

    mp4_path = Path(task.output_mp4_path)
    if not mp4_path.exists():
        raise HTTPException(status_code=410, detail="Output file no longer exists")

    file_size = mp4_path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        try:
            units, range_spec = range_header.split("=", 1)
            if units.strip().lower() != "bytes":
                raise ValueError("Only bytes range is supported")
            start_str, end_str = range_spec.split("-", 1)
            if start_str.strip() == "":
                # suffix-byte-range-spec: bytes=-N
                suffix_len = int(end_str)
                start = max(file_size - suffix_len, 0)
                end = file_size - 1
            else:
                start = int(start_str)
                end = int(end_str) if end_str.strip() else file_size - 1
            if start < 0 or end < start or end >= file_size:
                raise ValueError("Invalid range")
        except Exception:
            raise HTTPException(status_code=416, detail="Invalid Range header")

        chunk_size = 1024 * 1024

        def iter_file_range(path: Path, start_pos: int, end_pos: int):
            with open(path, "rb") as f:
                f.seek(start_pos)
                remaining = end_pos - start_pos + 1
                while remaining > 0:
                    read_size = min(chunk_size, remaining)
                    data = f.read(read_size)
                    if not data:
                        break
                    yield data
                    remaining -= len(data)

        disposition = "attachment" if as_attachment else "inline"
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
            "Content-Disposition": f'{disposition}; filename="{mp4_path.name}"',
        }
        return StreamingResponse(
            iter_file_range(mp4_path, start, end),
            status_code=206,
            media_type="video/mp4",
            headers=headers,
        )

    if as_attachment:
        return FileResponse(
            path=str(mp4_path),
            media_type="video/mp4",
            filename=mp4_path.name,
            headers={"Accept-Ranges": "bytes"},
        )

    return FileResponse(
        path=str(mp4_path),
        media_type="video/mp4",
        headers={
            "Content-Disposition": f'inline; filename="{mp4_path.name}"',
            "Accept-Ranges": "bytes",
        },
    )


@app.get("/v1/lodge/tasks/{task_id}/download-bvh")
def download_task_bvh(task_id: str) -> FileResponse:
    with _task_lock:
        task = _tasks.get(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if not task.output_bvh_path:
        raise HTTPException(status_code=409, detail="BVH not exported")

    bvh_path = Path(task.output_bvh_path)
    if not bvh_path.exists():
        raise HTTPException(status_code=410, detail="BVH file no longer exists")

    return FileResponse(path=str(bvh_path), media_type="application/octet-stream", filename=bvh_path.name)


@app.get("/v1/lodge/tasks/{task_id}/download-retarget")
def download_task_retarget_result(task_id: str, as_attachment: bool = False) -> FileResponse:
    with _task_lock:
        task = _tasks.get(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.retarget_status != "succeeded" or not task.output_retarget_mp4_path:
        raise HTTPException(status_code=409, detail="Retarget result not completed")

    mp4_path = Path(task.output_retarget_mp4_path)
    if not mp4_path.exists():
        raise HTTPException(status_code=410, detail="Retarget output file no longer exists")

    disposition = "attachment" if as_attachment else "inline"
    return FileResponse(
        path=str(mp4_path),
        media_type="video/mp4",
        filename=mp4_path.name if as_attachment else None,
        headers={
            "Content-Disposition": f'{disposition}; filename="{mp4_path.name}"',
            "Accept-Ranges": "bytes",
        },
    )

if __name__ == "__main__":
    access_log_enabled = os.getenv("LODGE_ACCESS_LOG", "0").strip().lower() in {"1", "true", "yes", "on"}
    uvicorn.run(app, host="0.0.0.0", port=8002, access_log=access_log_enabled)
