import os
import sys
import socket
import threading
import traceback
import uuid
import re
import shutil
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import copy
try:
    import lightning as L
except Exception:
    import pytorch_lightning as L
import numpy as np
import scipy.ndimage as filters
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from openai import OpenAI
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware


# Keep runtime stable on Windows scientific stacks.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent
DEFAULT_TASK_ROOT = APP_ROOT / "task_runs"
DEFAULT_TASK_ROOT.mkdir(parents=True, exist_ok=True)
SUBPROCESS_ENCODING = os.getenv("INTERGEN_SUBPROCESS_ENCODING", "utf-8")
SUBPROCESS_ERRORS = os.getenv("INTERGEN_SUBPROCESS_ERRORS", "replace")


def _looks_like_intergen_root(path: Path) -> bool:
    return (
        (path / "configs" / "model.yaml").exists()
        and (path / "configs" / "infer.yaml").exists()
        and (path / "models").exists()
        and (path / "utils" / "human_mesh_renderer_fast.py").exists()
        and (path / "utils" / "human_mesh_renderer.py").exists()
        and (path / "utils" / "human_model_paths.py").exists()
    )


def _detect_source_root() -> str:
    candidates = [
        PROJECT_ROOT,
        PROJECT_ROOT.parent / "InterGen" / "InterGen_master",
        PROJECT_ROOT / "InterGen" / "InterGen_master",
        Path(os.getenv("INTERGEN_SOURCE_ROOT_DEFAULT", "")).expanduser() if os.getenv("INTERGEN_SOURCE_ROOT_DEFAULT") else None,
        Path("D:/InterGen/InterGen_master"),
        Path("D:/HumanAction_Platform/InterGen/InterGen_master"),
        Path("D:/InterGen"),
    ]
    for c in candidates:
        if c is None:
            continue
        c = c.resolve()
        if _looks_like_intergen_root(c):
            return str(c)
    return ""

# Optional external source root that contains InterGen package folders like
# configs/, models/, and utils/. Useful when API code is separated from model code.
INTERGEN_SOURCE_ROOT = os.getenv("INTERGEN_SOURCE_ROOT", "").strip()
if not INTERGEN_SOURCE_ROOT:
    INTERGEN_SOURCE_ROOT = _detect_source_root()
if INTERGEN_SOURCE_ROOT:
    _source_root_path = Path(INTERGEN_SOURCE_ROOT).expanduser().resolve()
    if _source_root_path.exists() and str(_source_root_path) not in sys.path:
        sys.path.insert(0, str(_source_root_path))

# Optional external config directory. If provided, its parent is treated as the
# source root so `from configs import ...` remains importable.
INTERGEN_CONFIG_DIR = os.getenv("INTERGEN_CONFIG_DIR", "").strip()
if INTERGEN_CONFIG_DIR:
    _config_dir_path = Path(INTERGEN_CONFIG_DIR).expanduser().resolve()
    _config_parent = _config_dir_path.parent
    if _config_parent.exists() and str(_config_parent) not in sys.path:
        sys.path.insert(0, str(_config_parent))

# Ensure project modules are importable when running from this folder.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from collections import OrderedDict
from os.path import join as pjoin

from configs import get_config
from models import InterGen
from utils import paramUtil
from utils.human_mesh_renderer_fast import render_two_person_smpl_video_pyrender as render_two_person_smpl_video_fast
from utils.human_model_paths import get_human_models_root, validate_human_models
from utils.plot_script import plot_3d_motion
import utils.human_mesh_renderer_fast as _human_mesh_renderer_fast
import utils.human_mesh_renderer as _human_mesh_renderer
import utils.human_model_paths as _human_model_paths
try:
    from utils.utils import MotionNormalizer
except Exception:
    from utils.preprocess import MotionNormalizer

try:
    import configs as _configs_pkg

    CONFIGS_ROOT = Path(_configs_pkg.__file__).resolve().parent
    MODEL_SOURCE_ROOT = CONFIGS_ROOT.parent
except Exception:
    CONFIGS_ROOT = PROJECT_ROOT / "configs"
    MODEL_SOURCE_ROOT = PROJECT_ROOT


class GenerateMotionRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text prompt for two-person motion generation")
    num_samples: Optional[int] = Field(default=None, ge=1, le=8, description="Number of candidates to sample before selecting best")
    motion_frames: Optional[int] = Field(
        default=None,
        ge=180,
        le=210,
        description="Optional motion length in frames (180-210, equal to 6-7 seconds at 30 FPS)",
    )
    cfg_weight: Optional[float] = Field(default=None, ge=1.0, le=9.0, description="Optional classifier-free guidance weight")
    retarget_enabled: bool = Field(default=False, description="Export BVH and run Blender/Rokoko retarget for person1")
    retarget_strict: bool = Field(default=False, description="Fail the task if retargeting fails")
    target_fbx: Optional[str] = Field(default=None, description="Target character FBX path")
    mapping_file: Optional[str] = Field(default=None, description="Rokoko bone mapping JSON path")
    blender_executable: Optional[str] = Field(default=None, description="Blender executable path")
    retarget_script: Optional[str] = Field(default=None, description="Blender Python retarget script path")


class RetryRetargetRequest(BaseModel):
    retarget_strict: bool = Field(default=False, description="Fail the retry if retargeting fails")
    target_fbx: Optional[str] = Field(default=None, description="Target character FBX path")
    mapping_file: Optional[str] = Field(default=None, description="Rokoko bone mapping JSON path")
    blender_executable: Optional[str] = Field(default=None, description="Blender executable path")
    retarget_script: Optional[str] = Field(default=None, description="Blender Python retarget script path")
    motion_prompt: Optional[str] = Field(
        default=None,
        description="Optional prompt used to resolve an action-aware target spacing for historical tasks",
    )


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to be translated")
    target_lang: str = Field(default="English", description="Translation target language")


class TaskInfo(BaseModel):
    task_id: str
    status: str
    created_at: str
    updated_at: str
    message: str = ""
    progress: int = 0
    final_prompt: str = ""
    output_mp4_path: Optional[str] = None
    output_bvh_path: Optional[str] = None
    output_retarget_path: Optional[str] = None
    generated_frames: Optional[int] = None
    fps: Optional[int] = None
    duration_seconds: Optional[float] = None
    retarget_status: str = ""
    retarget_message: str = ""
    stdout_tail: str = ""
    stderr_tail: str = ""


class LitGenModel(L.LightningModule):
    def __init__(self, model, cfg):
        super().__init__()
        self.cfg = cfg
        self.automatic_optimization = False
        self.save_root = pjoin(self.cfg.GENERAL.CHECKPOINT, self.cfg.GENERAL.EXP_NAME)
        self.model_dir = pjoin(self.save_root, "model")
        self.meta_dir = pjoin(self.save_root, "meta")
        self.log_dir = pjoin(self.save_root, "log")
        os.makedirs(self.model_dir, exist_ok=True)
        os.makedirs(self.meta_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)
        self.model = model
        self.normalizer = MotionNormalizer()

    def _runtime_device(self) -> torch.device:
        return next(self.model.parameters()).device

    def plot_t2m(self, mp_data, result_path: str, caption: str):
        mp_joint = []
        for data in mp_data:
            joint = data[:, : 22 * 3].reshape(-1, 22, 3)
            mp_joint.append(joint)
        plot_3d_motion(result_path, paramUtil.t2m_kinematic_chain, mp_joint, title=caption, fps=30)

    def _resolve_window_size(self, prompt: str, motion_frames: Optional[int]) -> int:
        minimum_frames = _clamp_int(
            int(os.getenv("INTERGEN_MIN_MOTION_FRAMES", "180")),
            180,
            210,
        )
        maximum_frames = _clamp_int(
            int(os.getenv("INTERGEN_MAX_MOTION_FRAMES", "210")),
            minimum_frames,
            210,
        )
        if motion_frames is not None:
            return _clamp_int(motion_frames, minimum_frames, maximum_frames)

        default_frames = _clamp_int(
            int(os.getenv("INTERGEN_MOTION_FRAMES", "180")),
            minimum_frames,
            maximum_frames,
        )
        motion_profile = _motion_profile(prompt)
        if motion_profile == "boxing":
            combat_frames = _clamp_int(
                int(os.getenv("INTERGEN_COMBAT_MOTION_FRAMES", "210")),
                minimum_frames,
                maximum_frames,
            )
            return max(default_frames, combat_frames)
        if motion_profile in {"short_interaction", "fencing"}:
            return minimum_frames
        if motion_profile in {"dance", "running"}:
            return maximum_frames
        return default_frames

    def _resolve_request_cfg_weight(self, prompt: str, cfg_weight: Optional[float]) -> float:
        if cfg_weight is not None:
            return _clamp_float(cfg_weight, 1.0, 9.0)

        base = _clamp_float(float(os.getenv("INTERGEN_DEFAULT_REQUEST_CFG_WEIGHT", "5.0")), 1.0, 9.0)
        prompt_l = prompt.lower()
        if any(k in prompt_l for k in ["fencing", "fencer", "foil", "sabre", "sword", "duel"]):
            # Slightly lower CFG helps avoid frozen poses for highly dynamic duels.
            return min(base, 4.2)
        if any(k in prompt_l for k in ["fight", "boxing", "box", "punch", "kick"]):
            return min(base, 4.6)
        return base

    def generate_one_sample(
        self,
        prompt: str,
        output_path: str,
        motion_frames: Optional[int] = None,
        cfg_weight: Optional[float] = None,
    ) -> Dict[str, object]:
        self.model.eval()
        run_device = self._runtime_device()
        batch = OrderedDict({})
        batch["motion_lens"] = torch.zeros(1, 1, device=run_device).long()
        batch["prompt"] = prompt

        window_size = self._resolve_window_size(prompt, motion_frames)
        request_cfg_weight = self._resolve_request_cfg_weight(prompt, cfg_weight)

        old_cfg_weight = None
        if hasattr(self.model, "decoder") and hasattr(self.model.decoder, "cfg_weight"):
            old_cfg_weight = float(self.model.decoder.cfg_weight)
            self.model.decoder.cfg_weight = request_cfg_weight

        generation_attempts = max(1, _env_int("INTERGEN_GENERATION_ATTEMPTS_PER_SAMPLE", 2))
        motion_output = None
        frame_counts = []
        try:
            for attempt in range(1, generation_attempts + 1):
                motion_output = self.generate_loop(batch, window_size)
                frame_counts = [int(len(sequence)) for sequence in motion_output]
                if len(frame_counts) == 2 and all(count == window_size for count in frame_counts):
                    break
                print(
                    "[Generate] Frame-count mismatch: "
                    f"expected={window_size}, actual={frame_counts}, "
                    f"attempt={attempt}/{generation_attempts}"
                )
            else:
                raise RuntimeError(
                    "InterGen returned an invalid motion length after retries: "
                    f"expected={window_size}, actual={frame_counts}"
                )
        finally:
            if old_cfg_weight is not None:
                self.model.decoder.cfg_weight = old_cfg_weight

        generated_frames = int(frame_counts[0])
        raw_dir = Path(output_path).parent / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_joints_files = []
        for person_idx, joints3d in enumerate(motion_output, start=1):
            raw_path = raw_dir / f"{Path(output_path).stem}_person{person_idx}_joints22.npy"
            np.save(str(raw_path), joints3d.astype(np.float32))
            raw_joints_files.append(str(raw_path.resolve()))

        render_mode = os.getenv("INTERGEN_RENDER_MODE", "smpl").strip().lower()
        body_model_type = os.getenv("INTERGEN_BODY_MODEL", "smplx").strip().lower()
        profile_name = os.getenv("INTERGEN_RENDER_PROFILE", "balanced")
        defaults = _render_profile_defaults(profile_name)

        fps = int(os.getenv("INTERGEN_FPS", str(defaults["fps"])))
        num_fit_iters = int(os.getenv("INTERGEN_SMPL_ITERS", str(defaults["iters"])))
        max_render_frames = int(os.getenv("INTERGEN_MAX_RENDER_FRAMES", str(defaults["max_frames"])))
        camera_elev = float(os.getenv("INTERGEN_CAMERA_ELEV", str(defaults["camera_elev"])))
        camera_azim_env = os.getenv("INTERGEN_CAMERA_AZIM", str(defaults["camera_azim"]))
        camera_azim = None if camera_azim_env in (None, "", "auto", "AUTO") else float(camera_azim_env)
        camera_azim_offset = float(os.getenv("INTERGEN_CAMERA_AZIM_OFFSET", str(defaults["camera_azim_offset"])))
        camera_orbit_speed = float(os.getenv("INTERGEN_CAMERA_ORBIT_SPEED", str(defaults["camera_orbit_speed"])))
        render_size = _parse_render_size(
            os.getenv("INTERGEN_RENDER_SIZE", f"{defaults['size'][0]}x{defaults['size'][1]}"),
            default=defaults["size"],
        )
        ffmpeg_preset = os.getenv("INTERGEN_FFMPEG_PRESET", defaults["ffmpeg_preset"])
        ffmpeg_crf = int(os.getenv("INTERGEN_FFMPEG_CRF", str(defaults["ffmpeg_crf"])))
        dynamic_lighting = os.getenv("INTERGEN_DYNAMIC_LIGHTING", "1" if defaults["dynamic_lighting"] else "0").strip() == "1"
        align_with_stickman_axes = os.getenv(
            "INTERGEN_ALIGN_WITH_STICKMAN_AXES",
            "1" if defaults["align_with_stickman_axes"] else "0",
        ).strip() == "1"
        vertex_smooth_sigma = float(os.getenv("INTERGEN_VERTEX_SMOOTH_SIGMA", str(defaults["vertex_smooth_sigma"])))
        vertex_median_window = int(os.getenv("INTERGEN_VERTEX_MEDIAN_WINDOW", str(defaults["vertex_median_window"])))
        vertex_spike_z_thresh = float(os.getenv("INTERGEN_VERTEX_SPIKE_Z_THRESH", str(defaults["vertex_spike_z_thresh"])))
        min_duration_sec = max(6.0, float(os.getenv("INTERGEN_MIN_DURATION_SEC", str(defaults["min_duration_sec"]))))
        fit_early_stop_patience = int(os.getenv("INTERGEN_FIT_EARLY_STOP_PATIENCE", str(defaults["fit_early_stop_patience"])))
        fit_early_stop_check_every = int(os.getenv("INTERGEN_FIT_EARLY_STOP_CHECK_EVERY", str(defaults["fit_early_stop_check_every"])))
        fit_early_stop_rel_tol = float(os.getenv("INTERGEN_FIT_EARLY_STOP_REL_TOL", str(defaults["fit_early_stop_rel_tol"])))

        fps = _clamp_int(fps, 15, 30)
        camera_elev = _clamp_float(camera_elev, 0.0, 89.0)
        camera_azim_offset = _clamp_float(camera_azim_offset, -180.0, 180.0)
        camera_orbit_speed = _clamp_float(camera_orbit_speed, 0.0, 0.2)
        min_duration_sec = _clamp_float(min_duration_sec, 6.0, 20.0)
        target_duration_sec = generated_frames / float(max(fps, 1))
        vertex_median_window = _clamp_int(vertex_median_window, 1, 9)
        vertex_spike_z_thresh = _clamp_float(vertex_spike_z_thresh, 2.0, 10.0)
        if vertex_median_window % 2 == 0:
            vertex_median_window += 1

        force_stickman_axes = os.getenv("INTERGEN_FORCE_STICKMAN_AXES")
        if force_stickman_axes is not None:
            align_with_stickman_axes = force_stickman_axes.strip() == "1"

        print(f"[Render] mode={render_mode}")
        print("[Render] backend=fast")
        print(f"[Render] body_model={body_model_type}")
        print(f"[Render] profile={profile_name}")
        print(f"[Render] device={run_device}")
        print(f"[Render] request_cfg_weight={request_cfg_weight:.2f}")
        print(
            "[Render] effective "
            f"fps={fps}, dur_target={target_duration_sec:.2f}, dur_min={min_duration_sec:.2f}, "
            f"cam_elev={camera_elev:.1f}, cam_azim={('auto-front' if camera_azim is None else f'{camera_azim:.1f}')}, cam_azim_offset={camera_azim_offset:.1f}, stickman_axes={int(align_with_stickman_axes)}, "
            f"median_w={vertex_median_window}, sigma={vertex_smooth_sigma:.2f}, spike_z={vertex_spike_z_thresh:.2f}"
        )

        if render_mode == "smpl":
            human_models_root = _resolve_human_models_root()
            try:
                render_two_person_smpl_video_fast(
                    joints_a_22=motion_output[0],
                    joints_b_22=motion_output[1],
                    result_path=output_path,
                    human_models_root=human_models_root,
                    gender=os.getenv("INTERGEN_SMPL_GENDER", "neutral"),
                    fps=fps,
                    num_fit_iters=num_fit_iters,
                    device=run_device,
                    body_model_type=body_model_type,
                    max_render_frames=max_render_frames,
                    camera_elev=camera_elev,
                    camera_azim=camera_azim,
                    camera_azim_offset=camera_azim_offset,
                    camera_orbit_speed=camera_orbit_speed,
                    render_size=render_size,
                    ffmpeg_preset=ffmpeg_preset,
                    ffmpeg_crf=ffmpeg_crf,
                    dynamic_lighting=dynamic_lighting,
                    align_with_stickman_axes=align_with_stickman_axes,
                    vertex_smooth_sigma=vertex_smooth_sigma,
                    vertex_median_window=vertex_median_window,
                    vertex_spike_z_thresh=vertex_spike_z_thresh,
                    target_duration_sec=target_duration_sec,
                    min_duration_sec=min_duration_sec,
                    fit_early_stop_patience=fit_early_stop_patience,
                    fit_early_stop_check_every=fit_early_stop_check_every,
                    fit_early_stop_rel_tol=fit_early_stop_rel_tol,
                )
                return {
                    "render_mode": "smpl",
                    "message": "Task completed",
                    "fallback_used": "0",
                    "raw_joints_files": raw_joints_files,
                    "generated_frames": generated_frames,
                    "fps": fps,
                    "duration_seconds": round(target_duration_sec, 3),
                }
            except Exception as exc:
                strict_mode = os.getenv("INTERGEN_SMPL_STRICT", "0").strip() == "1"
                if strict_mode:
                    raise
                self.plot_t2m([motion_output[0], motion_output[1]], output_path, batch["prompt"])
                return {
                    "render_mode": "skeleton",
                    "message": "模型生成失败，回退至火柴人模型，请重新生成视频",
                    "fallback_used": "1",
                    "fallback_reason": str(exc),
                    "raw_joints_files": raw_joints_files,
                    "generated_frames": generated_frames,
                    "fps": fps,
                    "duration_seconds": round(target_duration_sec, 3),
                }
        else:
            self.plot_t2m([motion_output[0], motion_output[1]], output_path, batch["prompt"])
            return {
                "render_mode": "skeleton",
                "message": "Task completed (skeleton render mode)",
                "fallback_used": "0",
                "raw_joints_files": raw_joints_files,
                "generated_frames": generated_frames,
                "fps": fps,
                "duration_seconds": round(target_duration_sec, 3),
            }

    def generate_loop(self, batch, window_size):
        prompt = batch["prompt"]
        batch = copy.deepcopy(batch)
        batch["motion_lens"][:] = window_size
        sequences = [[], []]
        batch["text"] = [prompt]
        batch = self.model.forward_test(batch)
        motion_output_both = batch["output"][0].reshape(batch["output"][0].shape[0], 2, -1)
        motion_output_both = self.normalizer.backward(motion_output_both.cpu().detach().numpy())
        for j in range(2):
            motion_output = motion_output_both[:, j]
            joints3d = motion_output[:, : 22 * 3].reshape(-1, 22, 3)
            joints3d = filters.gaussian_filter1d(joints3d, 1, axis=0, mode="nearest")
            sequences[j].append(joints3d)
        sequences[0] = np.concatenate(sequences[0], axis=0)
        sequences[1] = np.concatenate(sequences[1], axis=0)
        return sequences


def _resolve_runtime_device(preferred: str = "cuda:0") -> torch.device:
    choice = (preferred or "cuda:0").strip().lower()
    if choice.startswith("cuda"):
        if torch.cuda.is_available():
            try:
                return torch.device(choice)
            except Exception:
                return torch.device("cuda:0")
        return torch.device("cpu")
    return torch.device("cpu")


def _parse_render_size(env_value: str, default=(960, 960)):
    value = (env_value or "").lower().strip()
    if "x" not in value:
        return default
    try:
        w_str, h_str = value.split("x", 1)
        width = max(320, int(w_str))
        height = max(320, int(h_str))
        return (width, height)
    except Exception:
        return default


def _render_profile_defaults(profile_name: str) -> dict:
    profile = (profile_name or "balanced").strip().lower()
    presets = {
        "fast": {
            "fps": 22,
            "iters": 60,
            "max_frames": 140,
            "size": (960, 960),
            "ffmpeg_preset": "ultrafast",
            "ffmpeg_crf": 22,
            "camera_elev": 18.0,
            "camera_azim": "auto",
            "camera_orbit_speed": 0.0,
            "camera_azim_offset": 0.0,
            "dynamic_lighting": False,
            "align_with_stickman_axes": True,
            "vertex_smooth_sigma": 0.6,
            "vertex_median_window": 3,
            "vertex_spike_z_thresh": 4.0,
            "target_duration_sec": 7.0,
            "min_duration_sec": 6.0,
            "fit_early_stop_patience": 5,
            "fit_early_stop_check_every": 5,
            "fit_early_stop_rel_tol": 2.0e-4,
        },
        "balanced": {
            "fps": 24,
            "iters": 120,
            "max_frames": 168,
            "size": (1280, 1280),
            "ffmpeg_preset": "veryfast",
            "ffmpeg_crf": 18,
            "camera_elev": 18.0,
            "camera_azim": "auto",
            "camera_orbit_speed": 0.0,
            "camera_azim_offset": 0.0,
            "dynamic_lighting": False,
            "align_with_stickman_axes": True,
            "vertex_smooth_sigma": 1.0,
            "vertex_median_window": 5,
            "vertex_spike_z_thresh": 3.0,
            "target_duration_sec": 7.0,
            "min_duration_sec": 6.0,
            "fit_early_stop_patience": 6,
            "fit_early_stop_check_every": 5,
            "fit_early_stop_rel_tol": 1.5e-4,
        },
        "quality": {
            "fps": 30,
            "iters": 200,
            "max_frames": 210,
            "size": (1440, 1440),
            "ffmpeg_preset": "medium",
            "ffmpeg_crf": 15,
            "camera_elev": 18.0,
            "camera_azim": "auto",
            "camera_orbit_speed": 0.0,
            "camera_azim_offset": 0.0,
            "dynamic_lighting": True,
            "align_with_stickman_axes": True,
            "vertex_smooth_sigma": 1.2,
            "vertex_median_window": 7,
            "vertex_spike_z_thresh": 3.0,
            "target_duration_sec": 7.0,
            "min_duration_sec": 6.0,
            "fit_early_stop_patience": 8,
            "fit_early_stop_check_every": 5,
            "fit_early_stop_rel_tol": 1.0e-4,
        },
    }
    return presets.get(profile, presets["balanced"])


def _clamp_int(x: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(x)))


def _clamp_float(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _build_model(model_cfg):
    if model_cfg.NAME != "InterGen":
        raise ValueError(f"Unsupported model config NAME: {model_cfg.NAME}")
    return InterGen(model_cfg)


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


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _motion_profile(prompt: str) -> str:
    prompt_l = (prompt or "").lower()
    if any(k in prompt_l for k in ["fencing", "fencer", "foil", "sabre", "sword", "duel", "击剑", "剑术"]):
        return "fencing"
    if any(k in prompt_l for k in [
        "fight", "fighting", "boxing", "boxer", "punch", "jab", "kick", "combat",
        "拳击", "格斗", "搏斗",
    ]):
        return "boxing"
    if any(k in prompt_l for k in ["dance", "dancing", "waltz", "tango", "跳舞", "舞蹈"]):
        return "dance"
    if any(k in prompt_l for k in ["run", "running", "jog", "jogging", "sprint", "奔跑", "跑步"]):
        return "running"
    if any(k in prompt_l for k in [
        "slap", "hit", "high five", "handshake", "shake hands", "hug", "embrace",
        "击掌", "握手", "拥抱",
    ]):
        return "short_interaction"
    return "default"


def _resolve_retarget_spacing(prompt: str) -> Tuple[str, float]:
    profile = _motion_profile(prompt)
    settings = {
        "dance": ("INTERGEN_RETARGET_DANCE_SPACING", 1.25),
        "boxing": ("INTERGEN_RETARGET_BOXING_SPACING", 0.45),
        "fencing": ("INTERGEN_RETARGET_FENCING_SPACING", 0.65),
        "running": ("INTERGEN_RETARGET_RUNNING_SPACING", 1.0),
        "short_interaction": ("INTERGEN_RETARGET_SHORT_INTERACTION_SPACING", 0.75),
        "default": ("INTERGEN_RETARGET_TARGET_SPACING", 1.0),
    }
    env_name, default_spacing = settings[profile]
    spacing = _clamp_float(float(os.getenv(env_name, str(default_spacing))), 0.0, 3.0)
    return profile, spacing


def _pick_best_candidate(candidates: list) -> dict:
    # Rank by the weaker person's post-correction result, not an aggregate that
    # can hide a poor second actor behind a clean first actor.
    def _rank(item: dict):
        fallback_used = 1 if str(item.get("fallback_used", "0")) == "1" else 0
        collision = item.get("self_collision") or {}
        hard_violation_count = int(collision.get("hard_violation_count", 0) or 0)
        max_person_ratio = float(collision.get("max_person_collision_ratio", 0.0) or 0.0)
        minimum_distance = collision.get("minimum_distance")
        minimum_distance = float(minimum_distance) if minimum_distance is not None else float("inf")
        collision_frames = int(collision.get("collision_frames", 0) or 0)
        penetration = float(collision.get("penetration_sum", 0.0) or 0.0)
        file_size = int(item.get("file_size", 0) or 0)
        return (
            fallback_used,
            hard_violation_count,
            max_person_ratio,
            -minimum_distance,
            collision_frames,
            penetration,
            -file_size,
        )

    return sorted(candidates, key=_rank)[0]


def _raw_hand_head_collision_metrics(raw_joints_files: List[str]) -> dict:
    from intergen_joints2bvh import (
        _correct_hand_head_collisions,
        _hand_head_metrics,
        _stabilize_upper_body_joints,
    )

    clearance_scale = max(0.1, float(os.getenv("INTERGEN_BVH_HAND_HEAD_CLEARANCE_SCALE", "2.0")))
    minimum_clearance = max(0.0, float(os.getenv("INTERGEN_BVH_HAND_HEAD_MIN_CLEARANCE", "0.15")))
    forearm_clearance_scale = max(
        0.1,
        float(os.getenv("INTERGEN_BVH_HAND_HEAD_FOREARM_CLEARANCE_SCALE", "1.5")),
    )
    forearm_minimum_clearance = max(
        0.0,
        float(os.getenv("INTERGEN_BVH_HAND_HEAD_FOREARM_MIN_CLEARANCE", "0.11")),
    )
    hard_ratio = max(0.0, float(os.getenv("INTERGEN_BVH_HARD_SELF_COLLISION_RATIO", "0.15")))
    hard_minimum_distance = max(
        0.0,
        float(os.getenv("INTERGEN_BVH_HARD_SELF_COLLISION_MIN_DISTANCE", "0.05")),
    )
    collision_frames = 0
    penetration_sum = 0.0
    minimum_distance = float("inf")
    max_person_collision_ratio = 0.0
    hard_violation_count = 0
    persons = []

    for person_idx, raw_file in enumerate(raw_joints_files, start=1):
        joints = np.load(str(raw_file), allow_pickle=False)
        if joints.ndim != 3 or joints.shape[1:] != (22, 3):
            continue
        if _env_flag("INTERGEN_BVH_UPPER_BODY_STABILIZATION", True):
            joints, _ = _stabilize_upper_body_joints(
                joints,
                upper_body_window=max(1, _env_int("INTERGEN_BVH_UPPER_BODY_JOINT_WINDOW", 5)),
                neck_window=max(1, _env_int("INTERGEN_BVH_NECK_JOINT_WINDOW", 7)),
                neck_max_position_correction=max(
                    0.0,
                    float(os.getenv("INTERGEN_BVH_NECK_MAX_POSITION_CORRECTION", "0.04")),
                ),
                head_max_position_correction=max(
                    0.0,
                    float(os.getenv("INTERGEN_BVH_HEAD_MAX_POSITION_CORRECTION", "0.03")),
                ),
            )
        head = joints[:, 15]
        head_lengths = np.linalg.norm(head - joints[:, 12], axis=-1)
        valid_head_lengths = head_lengths[head_lengths > 1e-6]
        head_length = float(np.median(valid_head_lengths)) if len(valid_head_lengths) else 0.0
        wrist_clearance = max(minimum_clearance, clearance_scale * head_length)
        forearm_clearance = max(
            forearm_minimum_clearance,
            forearm_clearance_scale * head_length,
        )
        if _env_flag("INTERGEN_BVH_HAND_HEAD_COLLISION", True):
            _, correction = _correct_hand_head_collisions(
                joints,
                clearance_scale=clearance_scale,
                minimum_clearance=minimum_clearance,
                forearm_clearance_scale=forearm_clearance_scale,
                forearm_minimum_clearance=forearm_minimum_clearance,
                blend_window=max(1, _env_int("INTERGEN_BVH_HAND_HEAD_BLEND_WINDOW", 7)),
                elbow_max_correction=max(
                    0.0,
                    float(os.getenv("INTERGEN_BVH_HAND_HEAD_ELBOW_MAX_CORRECTION", "0.03")),
                ),
                wrist_max_correction=max(
                    0.0,
                    float(os.getenv("INTERGEN_BVH_HAND_HEAD_MAX_CORRECTION", "0.05")),
                ),
            )
            metrics = correction["after"]
        else:
            metrics = _hand_head_metrics(joints, wrist_clearance, forearm_clearance)

        person_minimum_distance = float(metrics["minimum_distance"])
        person_collision_ratio = float(metrics["collision_ratio"])
        severe = (
            person_collision_ratio > hard_ratio
            or person_minimum_distance < hard_minimum_distance
        )
        minimum_distance = min(minimum_distance, person_minimum_distance)
        max_person_collision_ratio = max(max_person_collision_ratio, person_collision_ratio)
        penetration_sum += float(metrics["penetration_sum"])
        collision_frames += int(metrics["collision_frame_count"])
        hard_violation_count += int(severe)
        persons.append({
            "person": person_idx,
            "collision_frames": int(metrics["collision_frame_count"]),
            "collision_ratio": round(person_collision_ratio, 6),
            "minimum_distance": round(person_minimum_distance, 6),
            "penetration_sum": round(float(metrics["penetration_sum"]), 6),
            "hard_violation": severe,
        })

    return {
        "hard_violation_count": hard_violation_count,
        "max_person_collision_ratio": round(max_person_collision_ratio, 6),
        "collision_frames": collision_frames,
        "penetration_sum": round(penetration_sum, 6),
        "minimum_distance": round(minimum_distance, 6) if np.isfinite(minimum_distance) else None,
        "persons": persons,
    }


def _default_target_fbx() -> str:
    return str((PROJECT_ROOT.parent / "X Bot.fbx").resolve())


def _default_mapping_file() -> str:
    return str((PROJECT_ROOT.parent / "momask-main" / "assets" / "mapping.json").resolve())


def _default_retarget_script() -> str:
    return str((PROJECT_ROOT / "LODGE_api" / "blender_rokoko_retarget.py").resolve())


def _default_joints2bvh_script() -> str:
    return str((APP_ROOT / "intergen_joints2bvh.py").resolve())


def _resolve_optional_path(raw_value: Optional[str], env_name: str, default_value: str = "") -> Optional[Path]:
    raw = (raw_value or os.getenv(env_name, "") or default_value).strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def _run_subprocess(command: List[str], cwd: Path, timeout_sec: Optional[int] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding=SUBPROCESS_ENCODING,
        errors=SUBPROCESS_ERRORS,
        check=False,
        timeout=timeout_sec,
    )


def _export_intergen_bvh(task_id: str, task_root: Path, raw_joints_file: Path, person_idx: int = 1) -> Path:
    retarget_dir = task_root / "retarget"
    retarget_dir.mkdir(parents=True, exist_ok=True)
    output_bvh = retarget_dir / f"{task_id}_person{person_idx}.bvh"
    output_report = retarget_dir / f"{task_id}_person{person_idx}_bvh_report.json"
    script = _resolve_optional_path(None, "INTERGEN_JOINTS2BVH_SCRIPT", _default_joints2bvh_script())
    momask_root = _resolve_optional_path(None, "INTERGEN_MOMASK_ROOT", str((PROJECT_ROOT.parent / "momask-main").resolve()))
    if script is None or not script.exists():
        raise FileNotFoundError(f"INTERGEN_JOINTS2BVH_SCRIPT not found: {script}")
    if momask_root is None or not momask_root.exists():
        raise FileNotFoundError(f"INTERGEN_MOMASK_ROOT not found: {momask_root}")

    command = [
        sys.executable,
        str(script),
        "--input",
        str(raw_joints_file),
        "--output",
        str(output_bvh),
        "--momask-root",
        str(momask_root),
        "--fps",
        str(int(os.getenv("INTERGEN_FPS", "30"))),
        "--report",
        str(output_report),
    ]
    _update_task(task_id, message=f"Exporting InterGen person{person_idx} joints to BVH", progress=74)
    proc = _run_subprocess(command, cwd=APP_ROOT, timeout_sec=_env_int("INTERGEN_BVH_TIMEOUT_SEC", 900))
    if proc.returncode != 0 or not output_bvh.exists():
        raise RuntimeError(_last_nonempty_line(proc.stderr) or _last_nonempty_line(proc.stdout) or "InterGen BVH export failed")
    return output_bvh


def _run_intergen_retarget_if_requested(
    task_id: str,
    task_root: Path,
    output_path: Path,
    raw_joints_files: List[str],
    req: GenerateMotionRequest,
    motion_prompt: str = "",
) -> None:
    enabled = bool(req.retarget_enabled) or _env_flag("INTERGEN_RETARGET_ENABLED", False)
    if not enabled:
        _update_task(task_id, retarget_status="skipped", retarget_message="Retarget disabled")
        return

    strict = bool(req.retarget_strict) or _env_flag("INTERGEN_RETARGET_STRICT", False)
    if not raw_joints_files:
        message = "Retarget skipped, no raw joints files were generated"
        _update_task(task_id, retarget_status="skipped", retarget_message=message)
        if strict:
            raise RuntimeError(message)
        return

    try:
        source_bvhs = []
        for person_idx, raw_joints_file in enumerate(raw_joints_files[:2], start=1):
            source_bvhs.append(_export_intergen_bvh(task_id, task_root, Path(raw_joints_file).resolve(), person_idx=person_idx))
        if not source_bvhs:
            raise RuntimeError("No InterGen BVH files were exported")
        _update_task(task_id, output_bvh_path=";".join(str(path.resolve()) for path in source_bvhs))
    except Exception as exc:
        _update_task(task_id, retarget_status="failed", retarget_message=str(exc), stderr_tail=_tail_text(traceback.format_exc()))
        if strict:
            raise
        return

    blender_exe = _resolve_optional_path(req.blender_executable, "INTERGEN_BLENDER_EXE")
    target_fbx = _resolve_optional_path(req.target_fbx, "INTERGEN_TARGET_FBX", _default_target_fbx())
    mapping_file = _resolve_optional_path(req.mapping_file, "INTERGEN_RETARGET_MAPPING", _default_mapping_file())
    retarget_script = _resolve_optional_path(req.retarget_script, "INTERGEN_RETARGET_SCRIPT", _default_retarget_script())

    retarget_dir = task_root / "retarget"
    output_mp4 = retarget_dir / f"{task_id}_dual_retarget.mp4"
    report_path = retarget_dir / "rokoko_retarget_report.json"
    manifest_path = retarget_dir / "retarget_manifest.json"
    source_frame_counts = []
    for raw_joints_file in raw_joints_files[:2]:
        joints = np.load(str(raw_joints_file), mmap_mode="r", allow_pickle=False)
        source_frame_counts.append(int(joints.shape[0]))
    generated_frames = min(source_frame_counts) if source_frame_counts else 0
    manifest_fps = int(os.getenv("INTERGEN_FPS", "30"))
    effective_motion_prompt = _sanitize_prompt_text(motion_prompt or req.text)
    motion_profile, target_spacing = _resolve_retarget_spacing(effective_motion_prompt)
    manifest = {
        "task_id": task_id,
        "engine": "blender-rokoko",
        "source_bvh": str(source_bvhs[0].resolve()),
        "source_bvh_files": [str(path.resolve()) for path in source_bvhs],
        "source_bvh_reports": [
            str(path.with_name(f"{path.stem}_bvh_report.json").resolve())
            for path in source_bvhs
        ],
        "target_fbx": str(target_fbx),
        "mapping_file": str(mapping_file),
        "raw_joints_files": raw_joints_files,
        "source_preview_mp4": str(output_path.resolve()),
        "output_mp4": str(output_mp4.resolve()),
        "report_path": str(report_path.resolve()),
        "debug_blend": str((retarget_dir / "retarget_debug.blend").resolve()),
        "fps": manifest_fps,
        "source_frame_counts": source_frame_counts,
        "generated_frames": generated_frames,
        "duration_seconds": round(generated_frames / float(max(manifest_fps, 1)), 3),
        "max_render_frames": _env_int("INTERGEN_RETARGET_MAX_RENDER_FRAMES", 120),
        "render_size": os.getenv("INTERGEN_RETARGET_RENDER_SIZE", "1080x1080"),
        "camera_distance_scale": float(os.getenv("INTERGEN_RETARGET_CAMERA_DISTANCE_SCALE", "1.15")),
        "motion_prompt": effective_motion_prompt,
        "motion_profile": motion_profile,
        "target_spacing": target_spacing,
        "bvh_temporal_ik": _env_flag("INTERGEN_BVH_TEMPORAL_IK", True),
        "bvh_upper_body_stabilization": _env_flag("INTERGEN_BVH_UPPER_BODY_STABILIZATION", True),
        "bvh_neck_max_position_correction": float(
            os.getenv("INTERGEN_BVH_NECK_MAX_POSITION_CORRECTION", "0.04")
        ),
        "bvh_head_max_position_correction": float(
            os.getenv("INTERGEN_BVH_HEAD_MAX_POSITION_CORRECTION", "0.03")
        ),
        "bvh_root_anomaly_degrees": float(os.getenv("INTERGEN_BVH_ROOT_ANOMALY_DEGREES", "30.0")),
        "bvh_quality_gate": _env_flag("INTERGEN_BVH_QUALITY_GATE", True),
        "bvh_max_anomaly_ratio": float(os.getenv("INTERGEN_BVH_MAX_ANOMALY_RATIO", "0.10")),
        "bvh_max_ik_p95_error": float(os.getenv("INTERGEN_BVH_MAX_IK_P95_ERROR", "0.10")),
        "bvh_hand_head_collision": _env_flag("INTERGEN_BVH_HAND_HEAD_COLLISION", True),
        "bvh_hand_head_clearance_scale": float(
            os.getenv("INTERGEN_BVH_HAND_HEAD_CLEARANCE_SCALE", "2.0")
        ),
        "bvh_hand_head_min_clearance": float(
            os.getenv("INTERGEN_BVH_HAND_HEAD_MIN_CLEARANCE", "0.15")
        ),
        "bvh_hand_head_forearm_clearance_scale": float(
            os.getenv("INTERGEN_BVH_HAND_HEAD_FOREARM_CLEARANCE_SCALE", "1.5")
        ),
        "bvh_hand_head_forearm_min_clearance": float(
            os.getenv("INTERGEN_BVH_HAND_HEAD_FOREARM_MIN_CLEARANCE", "0.11")
        ),
        "bvh_hand_head_blend_window": _env_int("INTERGEN_BVH_HAND_HEAD_BLEND_WINDOW", 7),
        "bvh_hand_head_elbow_max_correction": float(
            os.getenv("INTERGEN_BVH_HAND_HEAD_ELBOW_MAX_CORRECTION", "0.03")
        ),
        "bvh_hand_head_max_correction": float(
            os.getenv("INTERGEN_BVH_HAND_HEAD_MAX_CORRECTION", "0.05")
        ),
        "bvh_max_self_collision_ratio": float(
            os.getenv("INTERGEN_BVH_MAX_SELF_COLLISION_RATIO", "0.02")
        ),
        "bvh_hard_self_collision_ratio": float(
            os.getenv("INTERGEN_BVH_HARD_SELF_COLLISION_RATIO", "0.15")
        ),
        "bvh_hard_self_collision_min_distance": float(
            os.getenv("INTERGEN_BVH_HARD_SELF_COLLISION_MIN_DISTANCE", "0.05")
        ),
        "core_smoothing_window": _env_int("INTERGEN_RETARGET_CORE_SMOOTHING_WINDOW", 5),
        "spine_smoothing_window": _env_int("INTERGEN_RETARGET_SPINE_SMOOTHING_WINDOW", 5),
        "core_max_rotation_degrees_per_frame": float(
            os.getenv("INTERGEN_RETARGET_CORE_MAX_ROTATION_DEGREES_PER_FRAME", "20.0")
        ),
        "spine_max_rotation_degrees_per_frame": float(
            os.getenv("INTERGEN_RETARGET_SPINE_MAX_ROTATION_DEGREES_PER_FRAME", "20.0")
        ),
        "core_max_acceleration_degrees_per_frame2": float(
            os.getenv("INTERGEN_RETARGET_CORE_MAX_ACCELERATION_DEGREES_PER_FRAME2", "6.0")
        ),
        "spine_max_acceleration_degrees_per_frame2": float(
            os.getenv("INTERGEN_RETARGET_SPINE_MAX_ACCELERATION_DEGREES_PER_FRAME2", "8.0")
        ),
        "chest_smoothing_window": _env_int("INTERGEN_RETARGET_CHEST_SMOOTHING_WINDOW", 5),
        "chest_max_rotation_degrees_per_frame": float(
            os.getenv("INTERGEN_RETARGET_CHEST_MAX_ROTATION_DEGREES_PER_FRAME", "18.0")
        ),
        "chest_max_acceleration_degrees_per_frame2": float(
            os.getenv("INTERGEN_RETARGET_CHEST_MAX_ACCELERATION_DEGREES_PER_FRAME2", "8.0")
        ),
        "neck_smoothing_window": _env_int("INTERGEN_RETARGET_NECK_SMOOTHING_WINDOW", 7),
        "neck_max_rotation_degrees_per_frame": float(
            os.getenv("INTERGEN_RETARGET_NECK_MAX_ROTATION_DEGREES_PER_FRAME", "15.0")
        ),
        "neck_max_acceleration_degrees_per_frame2": float(
            os.getenv("INTERGEN_RETARGET_NECK_MAX_ACCELERATION_DEGREES_PER_FRAME2", "6.0")
        ),
        "head_smoothing_window": _env_int("INTERGEN_RETARGET_HEAD_SMOOTHING_WINDOW", 7),
        "head_max_rotation_degrees_per_frame": float(
            os.getenv("INTERGEN_RETARGET_HEAD_MAX_ROTATION_DEGREES_PER_FRAME", "12.0")
        ),
        "head_max_acceleration_degrees_per_frame2": float(
            os.getenv("INTERGEN_RETARGET_HEAD_MAX_ACCELERATION_DEGREES_PER_FRAME2", "6.0")
        ),
        "head_world_stabilization_enabled": _env_flag(
            "INTERGEN_RETARGET_HEAD_WORLD_STABILIZATION_ENABLED", True
        ),
        "head_world_smoothing_window": _env_int("INTERGEN_RETARGET_HEAD_WORLD_SMOOTHING_WINDOW", 3),
        "head_world_max_rotation_degrees_per_frame": float(
            os.getenv("INTERGEN_RETARGET_HEAD_WORLD_MAX_ROTATION_DEGREES_PER_FRAME", "20.0")
        ),
        "head_world_max_acceleration_degrees_per_frame2": float(
            os.getenv("INTERGEN_RETARGET_HEAD_WORLD_MAX_ACCELERATION_DEGREES_PER_FRAME2", "6.0")
        ),
        "foot_lock_enabled": _env_flag("INTERGEN_RETARGET_FOOT_LOCK_ENABLED", True),
        "foot_lock_height_threshold": float(
            os.getenv("INTERGEN_RETARGET_FOOT_LOCK_HEIGHT_THRESHOLD", "0.065")
        ),
        "foot_lock_velocity_threshold": float(
            os.getenv("INTERGEN_RETARGET_FOOT_LOCK_VELOCITY_THRESHOLD", "0.08")
        ),
        "foot_lock_min_contact_frames": _env_int("INTERGEN_RETARGET_FOOT_LOCK_MIN_CONTACT_FRAMES", 3),
        "foot_lock_blend_frames": _env_int("INTERGEN_RETARGET_FOOT_LOCK_BLEND_FRAMES", 2),
        "foot_lock_max_correction": float(
            os.getenv("INTERGEN_RETARGET_FOOT_LOCK_MAX_CORRECTION", "0.15")
        ),
        "created_at": _utc_now(),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    required_paths = [blender_exe, target_fbx, mapping_file, retarget_script, *source_bvhs]
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
    _update_task(task_id, message="Running Blender/Rokoko retarget", progress=82, retarget_status="running")
    proc = _run_subprocess(command, cwd=retarget_dir, timeout_sec=_env_int("INTERGEN_RETARGET_TIMEOUT_SEC", 3600))
    if proc.returncode == 0 and output_mp4.exists():
        _update_task(
            task_id,
            output_retarget_path=str(output_mp4.resolve()),
            retarget_status="succeeded",
            retarget_message="Rokoko retarget completed",
            stdout_tail=_tail_text(proc.stdout or ""),
            stderr_tail=_tail_text(proc.stderr or ""),
        )
        return

    message = _last_nonempty_line(proc.stderr) or _last_nonempty_line(proc.stdout) or "Blender/Rokoko retarget failed"
    _update_task(
        task_id,
        retarget_status="failed",
        retarget_message=message,
        stdout_tail=_tail_text(proc.stdout or ""),
        stderr_tail=_tail_text(proc.stderr or ""),
    )
    if strict:
        raise RuntimeError(message)


def _resolve_human_models_root() -> str:
    # Priority: explicit env > model source root > API project root.
    env_root = os.getenv("INTERGEN_HUMAN_MODELS_ROOT", "").strip()
    if env_root:
        return str(Path(env_root).expanduser().resolve())

    source_default = MODEL_SOURCE_ROOT / "human_models"
    if source_default.exists():
        return str(source_default)

    return get_human_models_root(str(PROJECT_ROOT))


def _resolve_checkpoint_path(raw_checkpoint: str) -> Path:
    raw = (raw_checkpoint or "").strip()
    if not raw:
        raise FileNotFoundError("Empty checkpoint path")

    p = Path(raw).expanduser()
    candidates = []

    if p.is_absolute():
        candidates.append(p.resolve())
    else:
        candidates.append((MODEL_SOURCE_ROOT / p).resolve())
        candidates.append((PROJECT_ROOT / p).resolve())

    # Portable fallbacks for common InterGen workspace layouts.
    candidates.extend([
        (MODEL_SOURCE_ROOT.parent / "checkpoints" / "intergen.ckpt").resolve(),
        (PROJECT_ROOT.parent / "InterGen" / "checkpoints" / "intergen.ckpt").resolve(),
    ])

    seen = set()
    for c in candidates:
        key = str(c).lower()
        if key in seen:
            continue
        seen.add(key)
        if c.exists():
            return c

    return candidates[0]


class InterGenService:
    def __init__(self):
        self._model = None
        self._infer_lock = threading.Lock()

    def load(self):
        human_models_root = _resolve_human_models_root()
        status = validate_human_models(human_models_root)
        print("Human model assets:")
        print(f"  root: {status['human_models_root']}")
        print(f"  exists: {status['exists']}")
        print(f"  smpl_ready: {status['smpl_ready']}")
        print(f"  smplx_ready: {status['smplx_ready']}")
        print(f"  render_mode(default): {os.getenv('INTERGEN_RENDER_MODE', 'smpl')}")
        print("Code source resolution:")
        print(f"  INTERGEN_SOURCE_ROOT: {INTERGEN_SOURCE_ROOT or '(auto-not-found)'}")
        print(f"  CONFIGS_ROOT: {CONFIGS_ROOT}")
        print(f"  human_mesh_renderer_fast: {Path(_human_mesh_renderer_fast.__file__).resolve()}")
        print(f"  human_mesh_renderer: {Path(_human_mesh_renderer.__file__).resolve()}")
        print(f"  human_model_paths: {Path(_human_model_paths.__file__).resolve()}")
        if not status["smpl_ready"] and not status["smplx_ready"]:
            print("  note: SMPL assets unavailable, rendering may fall back to skeleton mode.")

        config_dir_env = os.getenv("INTERGEN_CONFIG_DIR", "").strip()
        config_dir = Path(config_dir_env).expanduser().resolve() if config_dir_env else CONFIGS_ROOT
        model_yaml = config_dir / "model.yaml"
        infer_yaml = config_dir / "infer.yaml"
        if not model_yaml.exists() or not infer_yaml.exists():
            raise FileNotFoundError(
                f"InterGen config files not found under: {config_dir}. "
                "Set INTERGEN_CONFIG_DIR to a directory that contains model.yaml and infer.yaml."
            )

        model_cfg = get_config(str(model_yaml))
        infer_cfg = get_config(str(infer_yaml))

        # yacs CfgNode loaded by get_config is frozen (immutable) by default.
        # Temporarily defrost to apply startup-locked inference overrides.
        model_cfg.defrost()

        # Lock startup inference config so same service name always uses the same core inference knobs.
        fixed_checkpoint_env = os.getenv("INTERGEN_FIXED_CHECKPOINT", "").strip()
        if fixed_checkpoint_env:
            ckpt_path = Path(fixed_checkpoint_env).expanduser().resolve()
            if not ckpt_path.exists():
                raise FileNotFoundError(f"INTERGEN_FIXED_CHECKPOINT not found: {ckpt_path}")
            checkpoint_source = "INTERGEN_FIXED_CHECKPOINT"
        else:
            ckpt_path = _resolve_checkpoint_path(str(model_cfg.CHECKPOINT))
            checkpoint_source = "model.yaml/CHECKPOINT(auto-resolved)"

        fixed_cfg_weight_raw = os.getenv("INTERGEN_FIXED_CFG_WEIGHT", "5.0").strip()
        fixed_strategy = os.getenv("INTERGEN_FIXED_SAMPLING_STRATEGY", "ddim50").strip() or "ddim50"
        cfg_weight = _clamp_float(float(fixed_cfg_weight_raw), 1.0, 9.0)

        model_cfg.CFG_WEIGHT = cfg_weight
        model_cfg.STRATEGY = fixed_strategy
        model_cfg.CHECKPOINT = str(ckpt_path)
        model_cfg.freeze()

        print("[Infer] Locked startup config:")
        print(f"  checkpoint_source: {checkpoint_source}")
        print(f"  checkpoint_path: {ckpt_path}")
        print(f"  cfg_weight: {model_cfg.CFG_WEIGHT}")
        print(f"  sampling_strategy: {model_cfg.STRATEGY}")

        model = _build_model(model_cfg)
        if model_cfg.CHECKPOINT:
            if not ckpt_path.exists():
                raise FileNotFoundError(f"Checkpoint not found: {ckpt_path}")
            ckpt = torch.load(str(ckpt_path), map_location="cpu")
            state_dict = ckpt.get("state_dict", {})
            for key in list(state_dict.keys()):
                if key.startswith("model."):
                    state_dict[key.replace("model.", "", 1)] = state_dict.pop(key)
            model.load_state_dict(state_dict, strict=False)

        preferred_device = os.getenv("INTERGEN_DEVICE", "cuda:0")
        device = _resolve_runtime_device(preferred_device)
        self._model = LitGenModel(model, infer_cfg).to(device)
        print(f"[Device] preferred={preferred_device}, selected={device}")

    def generate(
        self,
        prompt: str,
        output_path: Path,
        num_samples: Optional[int] = None,
        motion_frames: Optional[int] = None,
        cfg_weight: Optional[float] = None,
    ):
        if self._model is None:
            raise RuntimeError("Model not loaded")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with self._infer_lock:
            with torch.no_grad():
                default_samples = _env_int("INTERGEN_DEFAULT_NUM_SAMPLES", 5)
                prompt_l = prompt.lower()
                if num_samples is None and any(
                    k in prompt_l for k in ["fight", "fighting", "boxing", "boxing match", "boxers"]
                ):
                    default_samples = max(default_samples, _env_int("INTERGEN_COMBAT_NUM_SAMPLES", 2))
                sample_count = _clamp_int(num_samples if num_samples is not None else default_samples, 1, 8)
                candidate_dir = output_path.parent / "candidates"
                candidate_dir.mkdir(parents=True, exist_ok=True)

                candidates = []
                for i in range(sample_count):
                    candidate_path = candidate_dir / f"{output_path.stem}_sample{i+1}.mp4"
                    result = self._model.generate_one_sample(
                        prompt,
                        str(candidate_path),
                        motion_frames=motion_frames,
                        cfg_weight=cfg_weight,
                    )
                    if not candidate_path.exists():
                        raise FileNotFoundError(f"Expected sample output not found: {candidate_path}")
                    collision_metrics = _raw_hand_head_collision_metrics(
                        list((result or {}).get("raw_joints_files") or [])
                    )
                    candidates.append(
                        {
                            "path": candidate_path,
                            "file_size": candidate_path.stat().st_size,
                            "self_collision": collision_metrics,
                            **(result or {}),
                        }
                    )

                best = _pick_best_candidate(candidates)
                best_path = Path(best["path"])
                shutil.copy2(str(best_path), str(output_path))
                stable_raw_files = []
                raw_files = best.get("raw_joints_files") or []
                raw_dir = output_path.parent / "raw"
                raw_dir.mkdir(parents=True, exist_ok=True)
                for person_idx, raw_file in enumerate(raw_files, start=1):
                    src = Path(raw_file)
                    if not src.exists():
                        continue
                    dst = raw_dir / f"{output_path.stem}_person{person_idx}_joints22.npy"
                    shutil.copy2(str(src), str(dst))
                    stable_raw_files.append(str(dst.resolve()))

                keep_all = os.getenv("INTERGEN_KEEP_ALL_SAMPLES", "0").strip() == "1"
                if not keep_all:
                    for item in candidates:
                        p = Path(item["path"])
                        if p != best_path and p.exists():
                            p.unlink()

                best_idx = candidates.index(best) + 1
                summary_message = f"Best-of-{sample_count} selected sample #{best_idx}."
                merged = dict(best)
                merged["selected_sample"] = str(best_idx)
                merged["num_samples"] = str(sample_count)
                merged["raw_joints_files"] = stable_raw_files
                merged["message"] = f"{best.get('message', 'Task completed')} {summary_message}".strip()
                return merged


app = FastAPI(title="InterGen Async API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=1)
service = InterGenService()
_tasks: Dict[str, TaskInfo] = {}
_task_lock = threading.Lock()


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
        data["updated_at"] = _utc_now()
        _tasks[task_id] = TaskInfo(**data)


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _sanitize_prompt_text(text: str) -> str:
    cleaned = (text or "").strip().replace("\n", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"^(translation|translated|english)\s*[:：-]\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" \t\"'“”‘’")


def _optimize_prompt_for_intergen(text: str) -> str:
    prompt = _sanitize_prompt_text(text)
    if not prompt:
        return "Two people are interacting physically."

    if _contains_cjk(prompt):
        # Translation failed or returned mixed-language text.
        if any(k in prompt for k in ["奔跑", "跑步", "跑", "冲刺"]):
            return "Two people are happily running forward side by side with energetic arm swings, keeping a safe distance between them."
        if any(k in prompt for k in ["跳舞", "舞蹈", "舞"]):
            return "Two people are dancing together face to face with synchronized body movements."
        if any(k in prompt for k in ["握手"]):
            return "Two people are shaking hands while standing face to face."
        if any(k in prompt for k in ["拥抱", "抱"]):
            return "Two people are hugging each other while standing face to face."
        return "Two people are interacting physically while keeping a clear distance between their bodies."

    prompt_l = prompt.lower()

    if any(k in prompt_l for k in ["run", "running", "jog", "jogging", "sprint"]):
        return "Two people are happily running forward side by side with energetic arm swings, keeping a safe distance between them."
    if any(k in prompt_l for k in ["dance", "dancing", "waltz", "tango"]):
        return "Two people are dancing together face to face with synchronized body movements."
    if any(k in prompt_l for k in ["fencing", "fencer", "foil", "sabre", "sword", "duel"]):
        return "Two fencers are rapidly lunging, parrying, and stepping in an intense duel."
    if any(k in prompt_l for k in ["hug", "embrace"]):
        return "Two people approach, share a brief hug, release each other, and step back."
    if "high five" in prompt_l:
        return "Two people approach, raise their hands, exchange a high five, lower their arms, and step back."
    if any(k in prompt_l for k in ["fight", "boxing", "box", "punch", "kick"]):
        return (
            "In an intense boxing match, two people face each other in stable fighting stances. "
            "They alternate straight punches, blocks, and dodges while keeping their guarding hands clear of the head."
        )
    if any(k in prompt_l for k in ["handshake", "shake hands"]):
        return "Two people approach, shake hands briefly, release their hands, and step back."

    if not re.search(r"\b(two|2)\b", prompt_l):
        prompt = f"Two people are {prompt.rstrip('.')}"

    words = prompt.split()
    if len(words) > 24:
        prompt = " ".join(words[:24])
    if not prompt.endswith("."):
        prompt += "."
    return prompt


def _translate_if_needed(text: str) -> str:
    """
    If the text contains Chinese characters, attempt to translate to English using DashScope.
    If DashScope is not configured or errors occur, returns the original text to let the model try.
    """
    if not _contains_cjk(text):
        return _sanitize_prompt_text(text)

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("[Translate] Dashscope API Key missing, skipping translation.")
        return text

    base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        completion = client.chat.completions.create(
            model="qwen-mt-flash",
            messages=[{"role": "user", "content": text}],
            extra_body={
                "translation_options": {
                    "source_lang": "auto",
                    "target_lang": "English",
                }
            },
        )
        translated = completion.choices[0].message.content
        if translated:
            translated = _sanitize_prompt_text(translated)
            print(f"[Translate] {text} -> {translated}")
            return translated
    except Exception as e:
        print(f"[Translate] Error during translation: {e}")
    return _sanitize_prompt_text(text)


def _prepare_prompt_for_model(text: str) -> str:
    translated = _translate_if_needed(text)
    optimized = _optimize_prompt_for_intergen(translated)
    print(f"[Prompt] model_input={optimized}")
    return optimized


def _run_generate_task(task_id: str, req: GenerateMotionRequest) -> None:
    try:
        _update_task(task_id, status="running", message="Translating prompt...", progress=10)
        final_prompt = _prepare_prompt_for_model(req.text)

        _update_task(task_id, status="running", message="Generating motion...", progress=30)

        task_root = DEFAULT_TASK_ROOT / task_id
        output_path = task_root / "output" / f"{task_id}.mp4"

        render_result = service.generate(
            final_prompt,
            output_path,
            num_samples=req.num_samples,
            motion_frames=req.motion_frames,
            cfg_weight=req.cfg_weight,
        )

        if not output_path.exists():
            raise FileNotFoundError(f"Expected output not found: {output_path}")

        task_message = (render_result or {}).get("message", "Task completed")
        fallback_reason = (render_result or {}).get("fallback_reason", "")
        stderr_tail = _tail_text(fallback_reason) if fallback_reason else ""
        raw_joints_files = list((render_result or {}).get("raw_joints_files") or [])
        generated_frames = int((render_result or {}).get("generated_frames") or 0) or None
        generated_fps = int((render_result or {}).get("fps") or os.getenv("INTERGEN_FPS", "30"))
        duration_seconds = (
            round(generated_frames / float(max(generated_fps, 1)), 3)
            if generated_frames is not None
            else None
        )

        _run_intergen_retarget_if_requested(
            task_id=task_id,
            task_root=task_root,
            output_path=output_path,
            raw_joints_files=raw_joints_files,
            req=req,
            motion_prompt=final_prompt,
        )

        _update_task(
            task_id,
            status="succeeded",
            message=task_message,
            progress=100,
            final_prompt=final_prompt,
            output_mp4_path=str(output_path.resolve()),
            generated_frames=generated_frames,
            fps=generated_fps,
            duration_seconds=duration_seconds,
            stderr_tail=stderr_tail,
        )
    except Exception as exc:
        _update_task(
            task_id,
            status="failed",
            message=str(exc),
            progress=100,
            stderr_tail=_tail_text(traceback.format_exc()),
        )


def _existing_task_motion_files(task_id: str) -> Tuple[Path, Path, List[str]]:
    if Path(task_id).name != task_id or not re.fullmatch(r"[A-Za-z0-9_-]+", task_id):
        raise ValueError("Invalid task id")
    task_root = (DEFAULT_TASK_ROOT / task_id).resolve()
    if task_root.parent != DEFAULT_TASK_ROOT.resolve() or not task_root.is_dir():
        raise FileNotFoundError(f"Task directory not found: {task_id}")

    output_path = task_root / "output" / f"{task_id}.mp4"
    if not output_path.is_file():
        raise FileNotFoundError(f"SMPL preview not found: {output_path}")

    def _person_number(path: Path) -> int:
        match = re.search(r"_person(\d+)_joints22\.npy$", path.name)
        return int(match.group(1)) if match else 999

    raw_dir = task_root / "output" / "raw"
    raw_paths = sorted(raw_dir.glob(f"{task_id}_person*_joints22.npy"), key=_person_number)
    if len(raw_paths) < 2:
        raise FileNotFoundError(f"Expected two raw joints files under: {raw_dir}")
    return task_root, output_path, [str(path.resolve()) for path in raw_paths[:2]]


def _run_retry_retarget_task(task_id: str, req: RetryRetargetRequest) -> None:
    try:
        _update_task(
            task_id,
            status="running",
            message="Retrying retarget from existing joints...",
            progress=70,
            retarget_status="running",
            retarget_message="",
        )
        task_root, output_path, raw_joints_files = _existing_task_motion_files(task_id)
        retry_frame_counts = [
            int(np.load(path, mmap_mode="r", allow_pickle=False).shape[0])
            for path in raw_joints_files
        ]
        retry_frames = min(retry_frame_counts)
        retry_fps = int(os.getenv("INTERGEN_FPS", "30"))
        _update_task(
            task_id,
            generated_frames=retry_frames,
            fps=retry_fps,
            duration_seconds=round(retry_frames / float(max(retry_fps, 1)), 3),
        )
        with _task_lock:
            current_task = _tasks.get(task_id)
        retry_motion_prompt = (req.motion_prompt or (current_task.final_prompt if current_task else "")).strip()
        if not retry_motion_prompt:
            previous_manifest = task_root / "retarget" / "retarget_manifest.json"
            if previous_manifest.is_file():
                try:
                    previous_data = json.loads(previous_manifest.read_text(encoding="utf-8"))
                    retry_motion_prompt = str(previous_data.get("motion_prompt") or "").strip()
                except Exception:
                    retry_motion_prompt = ""
        retarget_req = GenerateMotionRequest(
            text="Retry existing InterGen motion retarget",
            retarget_enabled=True,
            retarget_strict=req.retarget_strict,
            target_fbx=req.target_fbx,
            mapping_file=req.mapping_file,
            blender_executable=req.blender_executable,
            retarget_script=req.retarget_script,
        )
        _run_intergen_retarget_if_requested(
            task_id=task_id,
            task_root=task_root,
            output_path=output_path,
            raw_joints_files=raw_joints_files,
            req=retarget_req,
            motion_prompt=retry_motion_prompt,
        )
        with _task_lock:
            current = _tasks.get(task_id)
        retarget_status = current.retarget_status if current else "failed"
        retarget_message = current.retarget_message if current else "Retarget retry state unavailable"
        if retarget_status != "succeeded":
            _update_task(
                task_id,
                status="succeeded",
                message="SMPL preview preserved; retarget retry did not complete",
                progress=100,
                output_mp4_path=str(output_path.resolve()),
            )
            return
        _update_task(
            task_id,
            status="succeeded",
            message="Retarget retry completed",
            progress=100,
            output_mp4_path=str(output_path.resolve()),
            retarget_message=retarget_message,
        )
    except Exception as exc:
        _update_task(
            task_id,
            status="failed" if req.retarget_strict else "succeeded",
            message="Retarget retry failed",
            progress=100,
            retarget_status="failed",
            retarget_message=str(exc),
            stderr_tail=_tail_text(traceback.format_exc()),
        )


@app.on_event("startup")
def _on_startup() -> None:
    service.load()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/translate")
def translate(req: TranslateRequest) -> Dict[str, str]:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="DASHSCOPE_API_KEY not configured")

    base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        completion = client.chat.completions.create(
            model="qwen-mt-flash",
            messages=[{"role": "user", "content": req.text}],
            extra_body={
                "translation_options": {
                    "source_lang": "auto",
                    "target_lang": req.target_lang,
                }
            },
        )
        translated = completion.choices[0].message.content
        if not translated:
            raise HTTPException(status_code=502, detail="Translation service returned empty response")
        return {"translation": translated}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/v1/intergen/tasks/generate", response_model=TaskInfo)
def create_generate_task(req: GenerateMotionRequest) -> TaskInfo:
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

    executor.submit(_run_generate_task, task_id, req)
    return task


@app.post("/v1/intergen/tasks/{task_id}/retry-retarget", response_model=TaskInfo)
def retry_task_retarget(task_id: str, req: RetryRetargetRequest) -> TaskInfo:
    try:
        _, output_path, _ = _existing_task_motion_files(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    with _task_lock:
        existing = _tasks.get(task_id)
        now = _utc_now()
        task = TaskInfo(
            task_id=task_id,
            status="queued",
            created_at=existing.created_at if existing else now,
            updated_at=now,
            message="Retarget retry queued",
            progress=65,
            final_prompt=existing.final_prompt if existing else "",
            output_mp4_path=str(output_path.resolve()),
            output_bvh_path=existing.output_bvh_path if existing else None,
            output_retarget_path=None,
            generated_frames=existing.generated_frames if existing else None,
            fps=existing.fps if existing else None,
            duration_seconds=existing.duration_seconds if existing else None,
            retarget_status="queued",
            retarget_message="",
        )
        _tasks[task_id] = task

    executor.submit(_run_retry_retarget_task, task_id, req)
    return task


@app.get("/v1/intergen/tasks/{task_id}", response_model=TaskInfo)
def get_task(task_id: str) -> TaskInfo:
    with _task_lock:
        task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/v1/intergen/tasks/{task_id}/download")
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


if __name__ == "__main__":
    host = os.getenv("INTERGEN_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.getenv("INTERGEN_PORT", "8001"))

    # Fail fast on port conflicts before model startup work.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
    except OSError:
        raise SystemExit(f"Port {port} is already in use. Set INTERGEN_PORT to another value and retry.")
    finally:
        probe.close()

    uvicorn.run(app, host=host, port=port)
