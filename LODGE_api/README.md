# LODGE Async API

This API wraps LODGE inference and rendering into asynchronous HTTP tasks.

## 1. Install

Run in this folder:

    pip install -r requirements.txt

## 2. Run

Option A (direct):

    python lodge_async_api.py

Option B (uvicorn):

    uvicorn lodge_async_api:app --host 0.0.0.0 --port 8002

Default port in current code is 8002.

## 3. Endpoint List

- GET /health
- POST /v1/lodge/tasks/render-song
- POST /v1/lodge/tasks/infer-and-render
- POST /v1/lodge/tasks/infer-from-audio
- POST /v1/lodge/tasks/infer-from-audio-upload
- POST /v1/lodge/tasks/render-from-npy-upload
- POST /v1/lodge/tasks/infer-from-feature-npy-upload
- GET /v1/lodge/tasks/{task_id}
- GET /v1/lodge/tasks/{task_id}/download
- GET /v1/lodge/tasks/{task_id}/download-bvh
- GET /v1/lodge/tasks/{task_id}/download-retarget
- POST /v1/lodge/tasks/{task_id}/open-output-folder
- POST /v1/lodge/tasks/{task_id}/open-output-player

Task status values:

- queued
- running
- succeeded
- failed

## 4. Core Workflows

### 4.1 Render from existing samples

POST /v1/lodge/tasks/render-song

JSON body example:

    {
      "lodge_root": "D:/LODGE-main",
      "sample_dir": "D:/LODGE-main/experiments/.../samples_dod_xxx",
      "song_id": "132",
      "python_executable": "D:/anaconda3/envs/lodge/python.exe",
      "mode": "smplx",
      "device": "0",
      "fps": 30
    }

### 4.2 Infer + render in one call

POST /v1/lodge/tasks/infer-and-render

JSON body example:

    {
      "lodge_root": "D:/LODGE-main",
      "song_id": "132",
      "python_executable": "D:/anaconda3/envs/lodge/python.exe",
      "infer_args": ["--soft", "1.0"],
      "mode": "smplx",
      "device": "0",
      "fps": 30
    }

Optional field:

- sample_dir_hint: force using a specific samples_dod directory.

### 4.3 Audio upload -> infer -> render

POST /v1/lodge/tasks/infer-from-audio-upload

multipart/form-data fields:

- lodge_root (required)
- song_id (required)
- audio_file (required)
- python_executable (optional)
- mode (optional, default smplx)
- device (optional, default 0)
- fps (optional, default 30)
- infer_args (optional, comma-separated string)

Supported uploaded audio/video formats are converted internally to wav when needed.

### 4.4 Feature npy upload -> infer -> render

POST /v1/lodge/tasks/infer-from-feature-npy-upload

multipart/form-data fields are similar to audio upload, with npy_file as the file field.

## 5. Query and Download

Query task:

    GET /v1/lodge/tasks/{task_id}

Task response includes progress (0-100), message, output_mp4_path, stdout_tail, stderr_tail.
It also includes output_npy_path, output_bvh_path, output_retarget_mp4_path, retarget_status, and retarget_message.

Download result mp4:

    GET /v1/lodge/tasks/{task_id}/download

Download exported BVH:

    GET /v1/lodge/tasks/{task_id}/download-bvh

Download retargeted character mp4 when retarget_status=succeeded:

    GET /v1/lodge/tasks/{task_id}/download-retarget

Supports:

- inline playback (default)
- attachment download with as_attachment=true
- HTTP Range requests

## 6. Desktop Helper Endpoints

For local deployment on the same machine:

- POST /v1/lodge/tasks/{task_id}/open-output-folder
- POST /v1/lodge/tasks/{task_id}/open-output-player

These endpoints open the output folder or mp4 using the backend host OS.

## 7. Notes

- The API wraps existing infer_lodge.py and render.py behavior.
- Every rendered motion npy is now exported to a same-name BVH in the task input directory.
- Optional Blender/Rokoko retargeting can be enabled per request with retarget_enabled=true or globally with LODGE_RETARGET_ENABLED=1.
- Retargeting environment variables:
  - LODGE_BLENDER_EXE: Blender executable path.
  - LODGE_TARGET_FBX: target character FBX path. Defaults to D:/HumanAction_Platform/X Bot.fbx when present.
  - LODGE_RETARGET_MAPPING: Rokoko mapping JSON path. Defaults to momask-main/assets/mapping.json.
  - LODGE_RETARGET_SCRIPT: Blender Python script path. Defaults to LODGE_api/blender_rokoko_retarget.py.
  - LODGE_RETARGET_STRICT: set 1 to fail the whole task when retargeting fails.
- Task state is kept in memory and will be lost after API restart.
- Outputs are stored under LODGE_api/task_runs/{task_id}/.

---

## 中文说明

该服务将 LODGE 推理与渲染封装为异步任务 API，适合前后端分离和本机联调。

### 1. 安装

在当前目录执行：

    pip install -r requirements.txt

### 2. 启动

方式一：

    python lodge_async_api.py

方式二：

    uvicorn lodge_async_api:app --host 0.0.0.0 --port 8002

当前代码默认端口为 8002。

### 3. 主要接口

- 健康检查：GET /health
- 任务创建：见上方 Endpoint List
- 查询任务：GET /v1/lodge/tasks/{task_id}
- 下载视频：GET /v1/lodge/tasks/{task_id}/download
- 打开目录：POST /v1/lodge/tasks/{task_id}/open-output-folder
- 打开播放器：POST /v1/lodge/tasks/{task_id}/open-output-player

### 4. 常用联调建议

1. 先调用创建任务接口，获取 task_id。
2. 轮询查询接口直到 status=succeeded 或 failed。
3. 成功后调用下载接口获取 mp4。

### 5. 备注

- 任务状态保存在内存中，服务重启后旧 task_id 会失效。
- 输出目录默认在 LODGE_api/task_runs/{task_id}/。
- 查询接口返回 progress 字段，可直接驱动前端进度条。
