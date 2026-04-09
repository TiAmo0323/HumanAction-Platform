# HumanAction-Platform

基于 InterGen 与 LODGE 的多模态人体动作生成平台，支持通过文本或音乐文件驱动生成视频，并提供前后端分离的异步任务接口。

本仓库包含：

- 前端 Web 页面（Vue 3 + Vite）
- InterGen 异步 API（文本驱动）
- LODGE 异步 API（音乐/特征驱动）

## 项目亮点

- 统一异步任务模式：提交任务、轮询状态、下载结果
- 支持文本驱动（InterGen）与音乐/特征驱动（LODGE）
- 前端内置任务轮询、进度展示、视频下载与本机播放器联动
- 支持 Windows 本地联调

## 当前功能状态

- 文本生成：可用（InterGen）
- 音乐/特征文件生成：可用（LODGE，支持 mp3/mp4/wav/npy）
- 语音模式：前端可切换，当前提交端未开放

## 技术架构

前端通过两个后端服务协同完成生成：

- InterGen API（默认 `http://127.0.0.1:8001`）
	- 负责文本动作生成与视频输出
- LODGE API（默认 `http://127.0.0.1:8002`）
	- 负责音乐/特征推理与渲染输出

前端默认调用关系见：

- [project/BACKEND_CALL_GUIDE.md](project/BACKEND_CALL_GUIDE.md)

## 目录结构

```text
HumanAction-Platform-main/
├─ InterGen_api/                # InterGen 异步服务
│  ├─ intergen_async_api.py
│  ├─ requirements.txt
│  └─ README.md
├─ LODGE_api/                   # LODGE 异步服务
│  ├─ lodge_async_api.py
│  ├─ requirements.txt
│  └─ README.md
└─ project/                     # 前端项目（Vue3 + Vite）
	 ├─ src/App.vue
	 ├─ BACKEND_CALL_GUIDE.md
	 └─ package.json
```

## 环境准备

建议使用 Conda，分别为 InterGen 与 LODGE 配置独立环境。

### 1) InterGen API 环境

```bash
cd InterGen_api
pip install -r requirements.txt
```

启动方式（推荐）：

```bash
start_intergen_api.bat
```

该脚本会自动设置常见运行变量（如 `INTERGEN_SOURCE_ROOT`、`INTERGEN_CONFIG_DIR`、`INTERGEN_HUMAN_MODELS_ROOT` 等）。

### 2) LODGE API 环境

```bash
cd LODGE_api
pip install -r requirements.txt
python lodge_async_api.py
```

### 3) 前端环境

```bash
cd project
npm install
npm run dev
```

## 前端环境变量

前端支持以下可选变量（未设置时使用默认值）：

- `VITE_INTERGEN_API_BASE`，默认 `http://127.0.0.1:8001`
- `VITE_LODGE_API_BASE`，默认 `http://127.0.0.1:8002`
- `VITE_LODGE_PYTHON_EXECUTABLE`，可选，用于透传 LODGE 的 Python 路径

## 快速开始（本机联调）

1. 启动 InterGen API（8001）
2. 启动 LODGE API（8002）
3. 启动前端（Vite）
4. 在页面中测试：
	 - 文本输入：走 InterGen
	 - 上传 mp3/mp4/wav/npy：走 LODGE

## 接口文档

- 前后端联调说明：
	- [project/BACKEND_CALL_GUIDE.md](project/BACKEND_CALL_GUIDE.md)
- InterGen API 说明：
	- [InterGen_api/README.md](InterGen_api/README.md)
- LODGE API 说明：
	- [LODGE_api/README.md](LODGE_api/README.md)

## 开源模型参考

- InterGen: https://tr3e.github.io/intergen-page/
- LODGE: https://li-ronghui.github.io/lodge

## 常见问题

### 1. 任务查询返回 404

两个后端当前都使用内存保存任务状态，服务重启后旧任务会失效，需要重新提交。

### 2. 前端进度条不连续

- LODGE 返回真实 `progress`，前端按真实进度显示。
- InterGen 当前不返回 `progress`，前端会使用模拟进度并在完成后置为 100%。

### 3. “打开播放器/打开文件夹”无效

这两个动作由 LODGE 后端所在机器执行。若是远端部署或无桌面权限，建议直接使用下载接口。

## 说明

本项目当前侧重本机联调与演示流程；生产部署建议补充持久化任务存储、鉴权、日志追踪和资源隔离策略。
