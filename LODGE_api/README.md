# LODGE Async API

This service wraps LODGE rendering as an asynchronous HTTP API, so backend and model code can live in different directories or machines.

## 1. Install

```bash
pip install -r api/requirements.txt
```

## 2. Run

```bash
uvicorn api.lodge_async_api:app --host 0.0.0.0 --port 8001
```

## 3. API Flow

1. Submit render task
2. Poll task status
3. Download mp4 when task succeeded

You can also submit a full infer+render task in one call.

### 3.1 Submit Task

`POST /v1/lodge/tasks/render-song`

Request body example:

```json
{
  "lodge_root": "D:/LODGE-main",
  "sample_dir": "D:/LODGE-main/experiments/Local_Module/FineDance_FineTuneV2_Local/samples_dod_2999_299_inpaint_soft_ddim_notranscontrol_2026-03-18-23-59-44",
  "song_id": "132",
  "python_executable": "D:/anaconda3/envs/lodge/python.exe",
  "mode": "smplx",
  "device": "0",
  "fps": 30
}
```

### 3.1.1 Submit Infer + Render Task

`POST /v1/lodge/tasks/infer-and-render`

Request body example:

```json
{
  "lodge_root": "D:/LODGE-main",
  "song_id": "132",
  "python_executable": "D:/anaconda3/envs/lodge/python.exe",
  "infer_args": ["--soft", "1.0"],
  "mode": "smplx",
  "device": "0",
  "fps": 30
}
```

Optional field: `sample_dir_hint`. If provided, rendering uses that specific samples directory; otherwise the latest `samples_dod_*` under `experiments` is auto-detected.

### 3.2 Query Task

`GET /v1/lodge/tasks/{task_id}`

Task statuses: `queued`, `running`, `succeeded`, `failed`.

### 3.3 Download MP4

`GET /v1/lodge/tasks/{task_id}/download`

Returns `video/mp4` file stream.

## 4. Notes

- This API currently wraps `render.py` for a given `song_id` from `sample_dir/concat/npy/{song_id}.npy`.
- Infer endpoint runs existing `infer_lodge.py` as-is, then renders one song id.
- It does not modify existing LODGE inference code.
- In-memory task state will be lost if the API process restarts.

---

## 中文说明

该服务将 LODGE 推理/渲染能力封装为异步 HTTP API，适合后端工程与模型工程分离部署的场景。

### 1. 安装依赖

```bash
pip install -r api/requirements.txt
```

### 2. 启动服务

```bash
uvicorn api.lodge_async_api:app --host 0.0.0.0 --port 8001
```

### 3. 接口调用流程

1. 提交异步任务
2. 轮询任务状态
3. 任务成功后下载 MP4

### 3.1 提交渲染任务（已有 samples 目录）

`POST /v1/lodge/tasks/render-song`

请求体示例：

```json
{
  "lodge_root": "D:/LODGE-main",
  "sample_dir": "D:/LODGE-main/experiments/Local_Module/FineDance_FineTuneV2_Local/samples_dod_2999_299_inpaint_soft_ddim_notranscontrol_2026-03-18-23-59-44",
  "song_id": "132",
  "python_executable": "D:/anaconda3/envs/lodge/python.exe",
  "mode": "smplx",
  "device": "0",
  "fps": 30
}
```

参数说明：

- `lodge_root`: LODGE 项目根目录。
- `sample_dir`: 已生成结果目录，要求包含 `concat/npy/{song_id}.npy`。
- `song_id`: 目标歌曲编号（如 `132`）。
- `python_executable`: LODGE conda 环境中的 Python 路径。
- `mode`: 渲染模式，可选 `smpl` / `smplh` / `smplx`。
- `device`: GPU 设备号字符串。
- `fps`: 输出视频帧率。

### 3.1.1 提交推理+渲染一体化任务

`POST /v1/lodge/tasks/infer-and-render`

请求体示例：

```json
{
  "lodge_root": "D:/LODGE-main",
  "song_id": "132",
  "python_executable": "D:/anaconda3/envs/lodge/python.exe",
  "infer_args": ["--soft", "1.0"],
  "mode": "smplx",
  "device": "0",
  "fps": 30
}
```

可选字段：`sample_dir_hint`。
如果提供该字段，渲染会优先使用该 samples 目录；如果不提供，则自动从 `experiments` 下选择最新的 `samples_dod_*` 目录。

### 3.2 查询任务状态

`GET /v1/lodge/tasks/{task_id}`

任务状态包括：`queued`、`running`、`succeeded`、`failed`。

### 3.3 下载结果视频

`GET /v1/lodge/tasks/{task_id}/download`

返回 `video/mp4` 文件流，后端可直接落盘保存。

### 4. 备注

- 当前封装基于现有 `render.py` 与 `infer_lodge.py`，不改动模型原始推理逻辑。
- 服务进程重启后，内存中的任务状态会丢失。
- 建议后端在拿到下载流后自行保存文件并维护业务侧文件路径/URL 映射。
