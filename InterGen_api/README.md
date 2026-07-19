# InterGen Async API

This folder provides an async HTTP API for text-to-motion generation and optional translation.

## 1. Endpoint List

- GET /health
- POST /translate
- POST /v1/intergen/tasks/generate
- POST /v1/intergen/tasks/{task_id}/retry-retarget
- GET /v1/intergen/tasks/{task_id}
- GET /v1/intergen/tasks/{task_id}/download
- GET /v1/intergen/retarget/characters

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
            "text": "Two people meet, shake hands, and walk together.",
            "retarget_enabled": true,
            "target_character_id": "x_bot",
            "retarget_mapping_profile": "mapping",
            "retarget_engine": "none",
            "retarget_strict": false
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

Task response includes these retarget fields:

- output_retarget_path
- retarget_status
- retarget_message

### 4.3 List retarget characters

GET /v1/intergen/retarget/characters

Typical response includes character_id, fbx existence, and mapping profiles.

### 4.4 Retry retarget without regenerating motion

POST /v1/intergen/tasks/{task_id}/retry-retarget

Use an empty JSON object to reuse the startup BAT configuration:

    {}

This reuses the task's existing two `joints22.npy` files, regenerates BVH, and runs Blender again. It does not rerun translation or InterGen inference.

### 4.5 Download result

GET /v1/intergen/tasks/{task_id}/download

Returns video/mp4 when task is succeeded.

### 4.6 Translate text

POST /translate

JSON body:

    {
            "text": "两个人面对面打招呼，然后一起向左移动。",
      "target_lang": "English"
    }

Translation env requirements:

- required: DASHSCOPE_API_KEY
- optional: DASHSCOPE_BASE_URL (default <https://dashscope.aliyuncs.com/compatible-mode/v1>)

Retarget env options:

- INTERGEN_RETARGET_CONFIG (optional, defaults to InterGen_api/retarget_characters.json)
- INTERGEN_RETARGET_COMMAND (optional, external command template)
- INTERGEN_BLENDER_EXE (required when using Blender bridge)
- INTERGEN_KEEMAP_SCRIPT (required when using Blender bridge)
- INTERGEN_MIN_MOTION_FRAMES (default 180; hard minimum of six seconds at 30 FPS)
- INTERGEN_MOTION_FRAMES (default 180; ordinary and short interactions use six seconds)
- INTERGEN_MAX_MOTION_FRAMES (default 210; hard maximum of seven seconds at 30 FPS)
- INTERGEN_COMBAT_MOTION_FRAMES (default 210; seven seconds at 30 FPS)
- INTERGEN_GENERATION_ATTEMPTS_PER_SAMPLE (default 2; retries an invalid frame count before rendering)
- INTERGEN_COMBAT_NUM_SAMPLES (default 2 in the retarget BAT; other motions remain Best-of-1)
- INTERGEN_RETARGET_TARGET_SPACING (default 1.0 meters for unclassified motions)
- INTERGEN_RETARGET_DANCE_SPACING (default 1.25 meters)
- INTERGEN_RETARGET_BOXING_SPACING (default 0.45 meters)
- INTERGEN_RETARGET_FENCING_SPACING (default 0.65 meters)
- INTERGEN_RETARGET_RUNNING_SPACING (default 1.0 meters)
- INTERGEN_RETARGET_SHORT_INTERACTION_SPACING (default 0.75 meters for handshakes, hugs, and high fives)
- INTERGEN_BVH_HAND_HEAD_COLLISION (default 1; enables hand/head self-collision correction)
- INTERGEN_BVH_HAND_HEAD_CLEARANCE_SCALE (default 2.0 times the head-joint length)
- INTERGEN_BVH_HAND_HEAD_MIN_CLEARANCE (default 0.15 meters)
- INTERGEN_BVH_HAND_HEAD_FOREARM_CLEARANCE_SCALE (default 1.5 times the head-joint length)
- INTERGEN_BVH_HAND_HEAD_FOREARM_MIN_CLEARANCE (default 0.11 meters)
- INTERGEN_BVH_HAND_HEAD_BLEND_WINDOW (default 7 frames)
- INTERGEN_BVH_HAND_HEAD_ELBOW_MAX_CORRECTION (default 0.03 meters)
- INTERGEN_BVH_HAND_HEAD_MAX_CORRECTION (default 0.05 meters for the wrist)
- INTERGEN_BVH_MAX_SELF_COLLISION_RATIO (default 0.02; residual collisions above this become warnings)
- INTERGEN_BVH_HARD_SELF_COLLISION_RATIO (default 0.15; severe quality-gate threshold)
- INTERGEN_BVH_HARD_SELF_COLLISION_MIN_DISTANCE (default 0.05 meters; severe quality-gate threshold)
- INTERGEN_BVH_NECK_MAX_POSITION_CORRECTION (default 0.04 meters)
- INTERGEN_BVH_HEAD_MAX_POSITION_CORRECTION (default 0.03 meters)

## 5. Render Behavior Notes

- Generated motion is constrained to 180-210 frames. Short interactions and fencing use 180 frames; combat, dance, and running use 210 frames.
- SMPL, BVH, and retarget videos use the generated joints frame count instead of independently stretching the video.
- Retarget character spacing is action-aware. The resolved motion profile, prompt, and spacing are stored in `retarget_manifest.json` and `rokoko_retarget_report.json`.
- Default mode prioritizes SMPL/SMPLX rendering.
- If SMPL rendering fails and strict mode is not enabled, API falls back to skeleton rendering.
- In fallback case, task can still be succeeded, and message may indicate fallback.

Typical messages:

- Task completed
- 模型生成失败，回退至火柴人模型，请重新生成视频

Outputs are stored under InterGen_api/task_runs/{task_id}/output/.

## 5.1 Retarget Command Bridge (recommended)

The startup script now injects a default command template that calls:

    InterGen_api/retarget_blender_bridge.py

This bridge forwards task manifest and file paths to Blender CLI. To enable real retargeting, set:

    set INTERGEN_BLENDER_EXE=C:\Program Files\Blender Foundation\Blender 4.2\blender.exe
    set INTERGEN_KEEMAP_SCRIPT=D:\YourPath\blender_keemap_retarget.py

Then start API with:

    start_intergen_api.bat

You can also edit and run:

    start_intergen_api_with_retarget_example.bat

Behavior:

- If `retarget_strict=false` and Blender command fails, task still succeeds and falls back to the preview copy (`retarget_status=failed`).
- If `retarget_strict=true`, retarget command failure causes the whole task to fail.

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
- GET /v1/intergen/retarget/characters

### 3. 任务流

1. 提交生成任务，拿到 task_id。
2. 轮询查询任务状态。
3. 成功后下载 mp4。

### 4. 重要说明

- 当前任务响应包含 progress 字段（0~100）。
- 创建任务可附带重定向参数：retarget_enabled、target_character_id、retarget_mapping_profile、retarget_engine、retarget_strict。
- 可通过 GET /v1/intergen/retarget/characters 查看角色配置是否生效。
- 输出目录默认在 InterGen_api/task_runs/{task_id}/output/。
- 若 SMPL 渲染失败，可能自动回退为火柴人渲染并返回成功状态，同时 message 给出提示。

### 5. 真实重定向最短配置

在启动 API 前设置（可写到系统环境变量或单次命令行）：

    set INTERGEN_BLENDER_EXE=C:\Program Files\Blender Foundation\Blender 4.2\blender.exe
    set INTERGEN_KEEMAP_SCRIPT=D:\YourPath\blender_keemap_retarget.py
    start_intergen_api.bat

说明：INTERGEN_KEEMAP_SCRIPT 是你自己的 Blender 自动化脚本，内部负责调用 KeeMap 插件完成 BVH->FBX 重定向，并导出 --output 指定的视频文件。
