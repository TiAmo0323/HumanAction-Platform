# InterGen Async API

This folder provides an async HTTP API for text-to-motion generation and optional translation.

## 1. Endpoint List

- GET /health
- POST /translate
- POST /v1/intergen/tasks/generate
- GET /v1/intergen/tasks/{task_id}
- GET /v1/intergen/tasks/{task_id}/download

Task status values:

- queued
- running
- succeeded
- failed

## 2. Run

Option A (recommended in this project):

    start_intergen_api.bat

Option B (direct):

    python intergen_async_api.py

Default port is 8001.

## 3. Runtime Environment

The bat script sets these common variables:

- INTERGEN_SOURCE_ROOT
- INTERGEN_CONFIG_DIR
- INTERGEN_HUMAN_MODELS_ROOT
- INTERGEN_RENDER_MODE
- INTERGEN_RENDER_BACKEND
- INTERGEN_RENDER_PROFILE
- INTERGEN_FPS
- INTERGEN_MAX_RENDER_FRAMES
- INTERGEN_BODY_MODEL
- INTERGEN_ALIGN_WITH_STICKMAN_AXES
- INTERGEN_FORCE_STICKMAN_AXES

If model/config paths are separated from this API wrapper, set INTERGEN_SOURCE_ROOT and INTERGEN_CONFIG_DIR explicitly.

## 4. Core API Usage

### 4.1 Create generation task

POST /v1/intergen/tasks/generate

JSON body example:

    {
      "text": "Two people meet, shake hands, and walk together."
    }

Typical response:

    {
      "task_id": "f8f65cbf-7d1b-4bbd-b2f5-589f09b8e5f7",
      "status": "queued",
      "created_at": "2026-03-27T12:00:00Z",
      "updated_at": "2026-03-27T12:00:00Z",
      "message": "Task queued",
      "output_mp4_path": null,
      "stderr_tail": ""
    }

### 4.2 Query task

GET /v1/intergen/tasks/{task_id}

Current task model does not include a numeric progress field.

### 4.3 Download result

GET /v1/intergen/tasks/{task_id}/download

Returns video/mp4 when task is succeeded.

### 4.4 Translate text

POST /translate

JSON body:

    {
      "text": "两个人面对面打招呼，然后一起向左移动。",
      "target_lang": "English"
    }

Translation env requirements:

- required: DASHSCOPE_API_KEY
- optional: DASHSCOPE_BASE_URL (default https://dashscope.aliyuncs.com/compatible-mode/v1)

## 5. Render Behavior Notes

- Default mode prioritizes SMPL/SMPLX rendering.
- If SMPL rendering fails and strict mode is not enabled, API falls back to skeleton rendering.
- In fallback case, task can still be succeeded, and message may indicate fallback.

Typical messages:

- Task completed
- 模型生成失败，回退至火柴人模型，请重新生成视频

Outputs are stored under InterGen_api/task_runs/{task_id}/output/.

## 6. Quick Curl Examples

Create task:

    curl -X POST "http://127.0.0.1:8001/v1/intergen/tasks/generate" -H "Content-Type: application/json" -d "{\"text\":\"两个人相遇，握手后并排向前行走。\"}"

Query task:

    curl "http://127.0.0.1:8001/v1/intergen/tasks/<task_id>"

Download task result:

    curl -L -o result.mp4 "http://127.0.0.1:8001/v1/intergen/tasks/<task_id>/download"

---

## 中文说明

本目录提供 InterGen 的异步任务 API，供前端/后端通过 HTTP 调用文本生成人体动作视频。

### 1. 启动方式

推荐直接运行：

    start_intergen_api.bat

或手动运行：

    python intergen_async_api.py

默认端口 8001。

### 2. 接口列表

- GET /health
- POST /translate
- POST /v1/intergen/tasks/generate
- GET /v1/intergen/tasks/{task_id}
- GET /v1/intergen/tasks/{task_id}/download

### 3. 任务流

1. 提交生成任务，拿到 task_id。
2. 轮询查询任务状态。
3. 成功后下载 mp4。

### 4. 重要说明

- 当前任务响应没有 progress 字段。
- 输出目录默认在 InterGen_api/task_runs/{task_id}/output/。
- 若 SMPL 渲染失败，可能自动回退为火柴人渲染并返回成功状态，同时 message 给出提示。

