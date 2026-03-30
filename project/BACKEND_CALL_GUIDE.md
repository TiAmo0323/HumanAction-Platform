# 舞蹈生成后端调用说明

本文档用于对接当前前端页面（`src/App.vue`）的后端接口。

## 1. 功能范围

前端当前支持 3 种生成模式：

- `text`：文字生成舞蹈
- `voice`：语音输入/上传语音文件生成舞蹈
- `music`：上传音乐文件生成舞蹈

支持分辨率：

- `720p`
- `1080p`
- `2k`

## 2. 推荐接口设计

### 2.1 创建生成任务

`POST /api/v1/dance/generations`

#### Content-Type

- `application/json`（text 模式）
- `multipart/form-data`（voice/music 模式，含文件上传）

#### 请求参数

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| mode | string | 是 | `text` / `voice` / `music` |
| resolution | string | 是 | `720p` / `1080p` / `2k` |
| prompt | string | text 模式必填 | 文本提示词 |
| file | file | voice/music 必填 | 音频文件（`audio/*`） |
| saveName | string | 否 | 输出文件名建议，如 `scene-1080p.mp4` |

#### 成功响应（202）

```json
{
  "jobId": "gen_20260328_001",
  "status": "queued",
  "progress": 0,
  "message": "task accepted"
}
```

---

### 2.2 查询任务状态

`GET /api/v1/dance/generations/{jobId}`

#### 成功响应（200）

```json
{
  "jobId": "gen_20260328_001",
  "status": "processing",
  "progress": 65,
  "previewUrl": "https://cdn.example.com/preview/gen_20260328_001.mp4",
  "resultUrl": null,
  "error": null
}
```

`status` 建议枚举：

- `queued`
- `processing`
- `succeeded`
- `failed`

当 `status = succeeded` 时，返回：

- `progress: 100`
- `resultUrl`：成品视频下载地址

---

### 2.3 下载结果（可选）

`GET /api/v1/dance/generations/{jobId}/download`

- 可直接 302 到对象存储地址
- 或直接返回流（`video/mp4`）

## 3. 与当前前端字段映射

前端状态字段（`src/App.vue`）与接口字段映射如下：

- `inputMode` -> `mode`
- `resolution` -> `resolution`
- `prompt` -> `prompt`
- 文件上传（`uploadFileInput`）-> `file`

前端当前进度条逻辑：

- 提交时先显示 `50%`
- 完成后变为 `100%`

建议升级为真实进度：

1. 创建任务后拿到 `jobId`
2. 每 1~2 秒轮询状态接口
3. 用返回的 `progress` 驱动进度条
4. `succeeded` 后展示/下载 `resultUrl`

## 4. 调用示例

### 4.1 text 模式

```bash
curl -X POST "http://localhost:8080/api/v1/dance/generations" \
  -H "Content-Type: application/json" \
  -d "{\"mode\":\"text\",\"resolution\":\"1080p\",\"prompt\":\"国风双人舞，慢镜头，舞台追光\"}"
```

### 4.2 voice 模式

```bash
curl -X POST "http://localhost:8080/api/v1/dance/generations" \
  -F "mode=voice" \
  -F "resolution=1080p" \
  -F "file=@voice-demo.wav"
```

### 4.3 music 模式

```bash
curl -X POST "http://localhost:8080/api/v1/dance/generations" \
  -F "mode=music" \
  -F "resolution=2k" \
  -F "file=@music-demo.mp3"
```

### 4.4 查询进度

```bash
curl "http://localhost:8080/api/v1/dance/generations/gen_20260328_001"
```

## 5. 错误码建议

| HTTP Code | 场景 | 建议 message |
|---|---|---|
| 400 | 参数缺失/非法 | invalid request |
| 413 | 文件过大 | file too large |
| 415 | 文件类型不支持 | unsupported media type |
| 422 | 模式与参数不匹配 | mode and payload mismatch |
| 500 | 服务内部错误 | internal error |
| 503 | 生成服务繁忙 | service unavailable |

## 6. 最低落地建议

后端最少先实现这 2 个接口即可完成联调：

1. `POST /api/v1/dance/generations`
2. `GET /api/v1/dance/generations/{jobId}`

这样前端就能完成：提交任务 -> 显示进度 -> 获取结果。
