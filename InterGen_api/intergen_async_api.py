import os
import sys
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import copy
import lightning as L
import numpy as np
import scipy.ndimage as filters
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from openai import OpenAI
from pydantic import BaseModel, Field


# Keep runtime stable on Windows scientific stacks.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent
DEFAULT_TASK_ROOT = APP_ROOT / "task_runs"
DEFAULT_TASK_ROOT.mkdir(parents=True, exist_ok=True)

# Ensure project modules are importable when running from this folder.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from collections import OrderedDict
from os.path import join as pjoin

from configs import get_config
from models import InterGen
from utils import paramUtil
from utils.human_mesh_renderer_fast import render_two_person_smpl_video_pyrender as render_two_person_smpl_video
from utils.human_model_paths import get_human_models_root, validate_human_models
from utils.plot_script import plot_3d_motion
from utils.preprocess import MotionNormalizer


class GenerateMotionRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text prompt for two-person motion generation")


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to be translated")
    target_lang: str = Field(default="English", description="Translation target language")


class TaskInfo(BaseModel):
    task_id: str
    status: str
    created_at: str
    updated_at: str
    message: str = ""
    output_mp4_path: Optional[str] = None
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

    def generate_one_sample(self, prompt: str, output_path: str) -> Dict[str, str]:
        self.model.eval()
        run_device = self._runtime_device()
        batch = OrderedDict({})
        batch["motion_lens"] = torch.zeros(1, 1, device=run_device).long()
        batch["prompt"] = prompt

        window_size = 210
        motion_output = self.generate_loop(batch, window_size)

        render_mode = os.getenv("INTERGEN_RENDER_MODE", "smpl").strip().lower()
        fps = int(os.getenv("INTERGEN_FPS", "24"))
        num_fit_iters = int(os.getenv("INTERGEN_SMPL_ITERS", "120"))
        max_render_frames = int(os.getenv("INTERGEN_MAX_RENDER_FRAMES", "168"))
        body_model_type = os.getenv("INTERGEN_BODY_MODEL", "smplx").strip().lower()

        if render_mode == "smpl":
            human_models_root = get_human_models_root(str(PROJECT_ROOT))
            try:
                render_two_person_smpl_video(
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
                )
                return {
                    "render_mode": "smpl",
                    "message": "Task completed",
                    "fallback_used": "0",
                }
            except Exception as exc:
                self.plot_t2m([motion_output[0], motion_output[1]], output_path, batch["prompt"])
                return {
                    "render_mode": "skeleton",
                    "message": "模型生成失败，回退至火柴人模型，请重新生成视频",
                    "fallback_used": "1",
                    "fallback_reason": str(exc),
                }
        else:
            self.plot_t2m([motion_output[0], motion_output[1]], output_path, batch["prompt"])
            return {
                "render_mode": "skeleton",
                "message": "Task completed (skeleton render mode)",
                "fallback_used": "0",
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


class InterGenService:
    def __init__(self):
        self._model = None
        self._infer_lock = threading.Lock()

    def load(self):
        human_models_root = get_human_models_root(str(PROJECT_ROOT))
        status = validate_human_models(human_models_root)
        print("Human model assets:")
        print(f"  root: {status['human_models_root']}")
        print(f"  exists: {status['exists']}")
        print(f"  smpl_ready: {status['smpl_ready']}")
        print(f"  smplx_ready: {status['smplx_ready']}")

        model_cfg = get_config(str(PROJECT_ROOT / "configs" / "model.yaml"))
        infer_cfg = get_config(str(PROJECT_ROOT / "configs" / "infer.yaml"))

        model = _build_model(model_cfg)
        if model_cfg.CHECKPOINT:
            ckpt_path = Path(model_cfg.CHECKPOINT)
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

    def generate(self, prompt: str, output_path: Path):
        if self._model is None:
            raise RuntimeError("Model not loaded")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with self._infer_lock:
            with torch.no_grad():
                return self._model.generate_one_sample(prompt, str(output_path))


app = FastAPI(title="InterGen Async API", version="1.0.0")
executor = ThreadPoolExecutor(max_workers=1)
service = InterGenService()
_tasks: Dict[str, TaskInfo] = {}
_task_lock = threading.Lock()


def _update_task(task_id: str, **kwargs) -> None:
    with _task_lock:
        task = _tasks.get(task_id)
        if task is None:
            return
        data = task.model_dump()
        data.update(kwargs)
        data["updated_at"] = _utc_now()
        _tasks[task_id] = TaskInfo(**data)


def _run_generate_task(task_id: str, req: GenerateMotionRequest) -> None:
    try:
        _update_task(task_id, status="running", message="Task is running")

        task_root = DEFAULT_TASK_ROOT / task_id
        output_path = task_root / "output" / f"{task_id}.mp4"

        render_result = service.generate(req.text, output_path)

        if not output_path.exists():
            raise FileNotFoundError(f"Expected output not found: {output_path}")

        task_message = (render_result or {}).get("message", "Task completed")
        fallback_reason = (render_result or {}).get("fallback_reason", "")
        stderr_tail = _tail_text(fallback_reason) if fallback_reason else ""

        _update_task(
            task_id,
            status="succeeded",
            message=task_message,
            output_mp4_path=str(output_path.resolve()),
            stderr_tail=stderr_tail,
        )
    except Exception as exc:
        _update_task(
            task_id,
            status="failed",
            message=str(exc),
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
    uvicorn.run(app, host="0.0.0.0", port=8001)
