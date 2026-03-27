# InterGen Async API

This folder hosts a web-oriented InterGen API that follows the async task style used by LODGE API.

本目录提供面向 Web 的 InterGen API，接口风格与 LODGE API 的异步任务模式保持一致。

## Endpoints

- `GET /health`
- `POST /translate`
- `POST /v1/intergen/tasks/generate`
- `GET /v1/intergen/tasks/{task_id}`
- `GET /v1/intergen/tasks/{task_id}/download`

## 接口说明（中文）

- `GET /health`
  - 用途：健康检查。
  - 返回：`{"status": "ok"}`。
- `POST /translate`
  - 用途：调用千问翻译接口。
  - 请求体：`text`（必填）、`target_lang`（可选，默认 `English`）。
- `POST /v1/intergen/tasks/generate`
  - 用途：提交 InterGen 动作生成任务（异步）。
  - 返回：任务信息（`task_id`、`status`、`message`、`stderr_tail` 等）。
  - 说明：默认优先走 SMPL/SMPLX 渲染；若渲染失败会自动回退为火柴人视频，任务状态仍为 `succeeded`，并在 `message` 中给出中文提示。
- `GET /v1/intergen/tasks/{task_id}`
  - 用途：查询任务状态。
  - 状态：`queued` / `running` / `succeeded` / `failed`。
- `GET /v1/intergen/tasks/{task_id}/download`
  - 用途：任务成功后下载生成的 mp4 文件。

## Run

1. Activate the InterGen Python environment.
2. From `InterGen_master` root, run:

```bash
python InterGen_api/intergen_async_api.py
```

Default port: `8001`.

## 启动方式（中文）

1. 激活 InterGen 对应的 Python 环境（建议与模型推理环境一致）。
2. 在 `InterGen_master` 根目录执行：

```bash
python InterGen_api/intergen_async_api.py
```

默认端口：`8001`。

## Request Example

```json
{
  "text": "Two people meet, shake hands, and walk together."
}
```

## 中文调用示例

### 1. 提交生成任务

```json
{
  "text": "两个人相遇，握手后并排向前行走。"
}
```

生成任务成功创建后的典型返回（`POST /v1/intergen/tasks/generate`）：

```json
{
  "task_id": "f8f65cbf-7d1b-4bbd-b2f5-589f09b8e5f7",
  "status": "queued",
  "created_at": "2026-03-27T12:00:00Z",
  "updated_at": "2026-03-27T12:00:00Z",
  "message": "Task queued",
  "output_mp4_path": null,
  "stderr_tail": ""
}
```

查询任务结果时（`GET /v1/intergen/tasks/{task_id}`）可能出现两种典型 `message`：

- 正常 SMPL/SMPLX 渲染完成：`Task completed`
- 渲染失败并自动回退火柴人：`模型生成失败，回退至火柴人模型，请重新生成视频`

若发生回退，`stderr_tail` 会包含回退前渲染异常的摘要，便于排查。

### 2. 翻译请求

```json
{
  "text": "两个人面对面打招呼，然后一起向左移动。",
  "target_lang": "English"
}
```

## Notes

- Model weights/config are loaded at startup.
- Rendering defaults use environment variables from existing InterGen runtime conventions.
- Task outputs are stored under `InterGen_api/task_runs/<task_id>/output/`.
- Translation endpoint uses Qwen MT via Dashscope-compatible OpenAI API.
- Required env for translation: `DASHSCOPE_API_KEY`.
- Optional env for translation: `DASHSCOPE_BASE_URL` (default: `https://dashscope.aliyuncs.com/compatible-mode/v1`).
- Motion rendering mode is controlled by `INTERGEN_RENDER_MODE` (default `smpl`).
- If `INTERGEN_RENDER_MODE` is not `smpl`, API generates skeleton video directly.

## 备注（中文）

- 服务启动时会自动加载模型配置与权重。
- 渲染参数默认沿用现有 InterGen 环境变量约定。
- 任务产物默认保存在 `InterGen_api/task_runs/<task_id>/output/`。
- 动作生成默认使用 `INTERGEN_RENDER_MODE=smpl`（即优先 SMPL/SMPLX 渲染）。
- 当 `INTERGEN_RENDER_MODE` 不是 `smpl` 时，会直接输出火柴人视频。
- 当 `INTERGEN_RENDER_MODE=smpl` 且渲染失败时，会自动回退到火柴人视频。
- 翻译接口通过 Dashscope 兼容 OpenAI 的方式调用千问模型。
- 翻译接口必需环境变量：`DASHSCOPE_API_KEY`。
- 翻译接口可选环境变量：`DASHSCOPE_BASE_URL`（默认 `https://dashscope.aliyuncs.com/compatible-mode/v1`）。
