# HumanAction-Platform

HumanAction-Platform 是一个面向 Windows 本地运行的多模态人体动作生成与动画重定向平台。项目目前集成了：

- **InterGen**：根据文本生成双人动作。
- **LODGE**：根据音乐或音频特征生成舞蹈动作。
- **SMPL/SMPL-X**：拟合并渲染人体模型预览。
- **BVH 导出**：在保存原始 `npy` 的同时输出骨骼动画。
- **Blender + Rokoko**：将 BVH 重定向到 FBX 动漫角色并渲染视频。
- **Vue 3 + Vite**：提供文本输入、文件上传、进度轮询和视频播放界面。

本文档根据 2026-07-19 的本地项目状态整理。

## 当前进度

### 已完成

- InterGen 中文/英文文本生成双人 SMPL 动作。
- 中文提示词通过千问翻译 API 转成英文后输入 InterGen。
- LODGE 支持上传 `mp3`、`mp4`、`wav` 和特征 `npy`。
- InterGen 和 LODGE 生成结果均可导出 BVH。
- Blender 后台调用 Rokoko 插件进行角色重定向。
- InterGen 已支持两个人物分别导出 BVH，并重定向到两个角色。
- 自动相机取景、核心骨骼旋转平滑、头颈稳定和脚步锁定。
- 手腕/前臂与头部的自碰撞修正，以及警告级/严重级 BVH 质量门。
- InterGen 默认输出 6～7 秒动作，并记录帧数、FPS 和实际时长。
- 重定向人物间距会根据舞蹈、拳击、击剑等动作类型自动调整。
- 已有 NPY 的 InterGen 任务可以只重试 BVH 和 Blender，无需重新运行动作生成。

### 当前限制

- InterGen 对训练集中较少见的动作语义不稳定，例如羽毛球、网球和持道具运动。
- 当前 SMPL/BVH 只描述人体动作，不包含球拍、剑、羽毛球等道具动画。
- 两个重定向角色默认都使用同一个 `X Bot.fbx`，尚未区分性别或角色外观。
- 任务状态主要保存在内存中，API 重启后原任务查询可能返回 404，但任务文件仍保留在磁盘。
- InterGen 的重定向 MP4 当前通过任务状态中的本地路径访问，尚未提供独立的 `download-retarget` 接口。
- 前端语音模式仍未开放。

## 系统架构

```text
文本提示词
  -> 千问翻译与提示词规范化
  -> InterGen 双人动作
  -> joints22 NPY
  -> SMPL/SMPL-X 预览 MP4
  -> 双人 BVH + 质量报告
  -> Blender + Rokoko
  -> 双角色重定向 MP4

音乐/特征文件
  -> LODGE 推理
  -> 动作 NPY
  -> SMPL/SMPL-X 预览 MP4
  -> BVH
  -> Blender + Rokoko
  -> 角色重定向 MP4
```

服务端口：

| 服务 | 默认地址 | 作用 |
|---|---|---|
| InterGen API | `http://127.0.0.1:8001` | 文本双人动作生成与重定向 |
| LODGE API | `http://127.0.0.1:8002` | 音乐动作生成与重定向 |
| Vue/Vite | `http://127.0.0.1:5173` | Web 前端 |

## 推荐目录结构

当前 BAT 按下面的目录关系查找模型、映射和角色文件：

```text
D:\HumanAction_Platform\
├─ HumanAction-Platform-main\
│  ├─ InterGen_api\
│  ├─ LODGE_api\
│  └─ project\
├─ InterGen\InterGen_master\
├─ LODGE-main\
├─ momask-main\
│  └─ assets\mapping.json
└─ X Bot.fbx

D:\Blender_4.2\
└─ blender.exe
```

`blender-launcher.exe` 用于打开 Blender 界面；后台重定向必须配置实际的 `blender.exe`。

## 关键文件

```text
HumanAction-Platform-main/
├─ README.md
├─ InterGen_api/
│  ├─ intergen_async_api.py             # 文本生成异步 API
│  ├─ intergen_joints2bvh.py            # 双人 joints22 -> BVH
│  ├─ start_intergen_api_retarget.bat   # 推荐启动脚本
│  ├─ task_runs/                         # InterGen 任务结果
│  └─ README.md
├─ LODGE_api/
│  ├─ lodge_async_api.py                # 音乐生成异步 API
│  ├─ blender_rokoko_retarget.py        # Blender/Rokoko 重定向脚本
│  ├─ start_lodge_api_retarget.bat      # 推荐启动脚本
│  ├─ task_runs/                         # LODGE 任务结果
│  └─ README.md
└─ project/
   ├─ src/App.vue
   ├─ BACKEND_CALL_GUIDE.md
   └─ package.json
```

## 环境准备

建议继续使用当前已经验证过的两个 Conda 环境：

| 模块 | 环境 | Python 路径 |
|---|---|---|
| InterGen | `intergen_01` | `D:\Anaconda\envs\intergen_01\python.exe` |
| LODGE | `lodge` | `D:\Anaconda\envs\lodge\python.exe` |

`requirements.txt` 是对应环境的依赖快照。PyTorch、CUDA 和 PyTorch3D 对版本较敏感，已有环境可用时不建议直接整体覆盖安装。

还需要：

- NVIDIA GPU 和匹配的 CUDA/PyTorch 环境。
- Blender 4.2。
- Blender 中安装并启用 Rokoko Studio Live 插件。
- 可用的 InterGen、LODGE、SMPL/SMPL-X 模型资源。
- 千问翻译所需的 `DASHSCOPE_API_KEY`。

在启动 InterGen API 的同一个 CMD 窗口设置翻译密钥：

```bat
set DASHSCOPE_API_KEY=你的密钥
```

可选配置：

```bat
set DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

若翻译接口返回 502，请先检查网络、代理或 VPN。翻译失败时系统会尝试使用本地提示词回退，但中文复杂动作的语义准确率会下降。

## 快速启动

建议分别打开三个 CMD/Anaconda Prompt 窗口。

### 1. 启动 InterGen 文本生成与重定向

```bat
conda activate intergen_01
cd /d D:\HumanAction_Platform\HumanAction-Platform-main\InterGen_api
start_intergen_api_retarget.bat
```

启动成功后检查：

```bat
curl http://127.0.0.1:8001/health
```

### 2. 启动 LODGE 音乐生成与重定向

```bat
conda activate lodge
cd /d D:\HumanAction_Platform\HumanAction-Platform-main\LODGE_api
start_lodge_api_retarget.bat
```

启动成功后检查：

```bat
curl http://127.0.0.1:8002/health
```

### 3. 启动前端

```bat
cd /d D:\HumanAction_Platform\HumanAction-Platform-main\project
npm install
npm run dev
```

浏览器打开 Vite 输出的地址，通常是 `http://127.0.0.1:5173`。

## InterGen 使用说明

### 创建文本任务

```bat
curl -X POST "http://127.0.0.1:8001/v1/intergen/tasks/generate" ^
  -H "Content-Type: application/json" ^
  -d "{\"text\":\"双方正在进行激烈的击剑比赛，脚步轻盈，动作敏捷。\"}"
```

返回的 `task_id` 用于查询：

```bat
curl "http://127.0.0.1:8001/v1/intergen/tasks/<task_id>"
```

任务结果包含：

- `final_prompt`：最终送入 InterGen 的英文提示词。
- `generated_frames`：生成帧数。
- `fps`：帧率。
- `duration_seconds`：实际时长。
- `output_mp4_path`：SMPL 预览。
- `output_bvh_path`：两个人的 BVH 路径。
- `output_retarget_path`：双角色重定向视频。
- `retarget_status` / `retarget_message`：重定向状态。

下载 SMPL 预览：

```bat
curl -L -o intergen_result.mp4 "http://127.0.0.1:8001/v1/intergen/tasks/<task_id>/download"
```

### 仅重试历史任务的重定向

```bat
curl -X POST "http://127.0.0.1:8001/v1/intergen/tasks/<task_id>/retry-retarget" ^
  -H "Content-Type: application/json" ^
  -d "{}"
```

该接口复用任务目录中已有的两份 `joints22.npy`，重新生成 BVH 并调用 Blender，不会重新运行翻译、InterGen 或 SMPL 拟合。

对于旧 manifest 没有动作提示词的任务，可以补充：

```json
{
  "motion_prompt": "Two fencers lunge and parry in an intense duel."
}
```

注意：重试重定向不会增加旧 NPY 的帧数。旧的 144 帧任务仍然只有 4.8 秒；要应用新的 6～7 秒策略必须重新生成动作。

## InterGen 时长与候选策略

当前统一使用 `30 FPS`：

| 动作类型 | 帧数 | 时长 | 默认候选数 |
|---|---:|---:|---:|
| 普通互动、握手、拥抱、击掌 | 180 | 6 秒 | 1 |
| 击剑 | 180 | 6 秒 | 1 |
| 拳击/格斗 | 210 | 7 秒 | 2 |
| 舞蹈、奔跑 | 210 | 7 秒 | 1 |

手动传入的 `motion_frames` 必须位于 `180～210`。模型返回的两个人帧数不符合目标时，单个候选最多自动生成两次。

拳击默认 Best-of-2；候选排序会优先考虑渲染是否成功，以及两个人中质量较差者在手/头碰撞修正后的指标。该排序主要筛除重定向风险，不等同于完整的文本语义评分。

## 动作感知人物间距

Rokoko 重定向保留 InterGen 原始双人根节点运动，同时在 X 轴增加静态偏移。当前 `start_intergen_api_retarget.bat` 使用：

| 动作类型 | 附加间距 |
|---|---:|
| 舞蹈 | 1.25 m |
| 拳击/格斗 | 0.41 m |
| 击剑 | 0.65 m |
| 握手/拥抱/击掌 | 0.75 m |
| 奔跑、普通动作 | 1.0 m |

动作类型、最终提示词和实际间距会写入 `retarget_manifest.json` 与 `rokoko_retarget_report.json`。这些值是额外偏移，不是人物之间每一帧的绝对距离；若原始动作本身移动范围很大，实际距离仍会变化。

## InterGen 输出目录

```text
InterGen_api/task_runs/<task_id>/
├─ output/
│  ├─ <task_id>.mp4
│  ├─ candidates/
│  └─ raw/
│     ├─ <task_id>_person1_joints22.npy
│     └─ <task_id>_person2_joints22.npy
└─ retarget/
   ├─ <task_id>_person1.bvh
   ├─ <task_id>_person2.bvh
   ├─ <task_id>_person1_bvh_report.json
   ├─ <task_id>_person2_bvh_report.json
   ├─ <task_id>_dual_retarget.mp4
   ├─ retarget_manifest.json
   ├─ rokoko_retarget_report.json
   └─ retarget_debug.blend
```

BVH 质量报告包括：

- 上半身和头颈关节稳定结果。
- 时间连续 IK 误差。
- 核心骨骼旋转异常与修复统计。
- 手腕/前臂与头部的碰撞修正前后指标。
- `warnings`：允许继续渲染的轻微问题。
- `violations`：会阻止 Blender 重定向的严重问题。

## LODGE 使用说明

前端常用两个上传接口：

- 音频/视频：`POST /v1/lodge/tasks/infer-from-audio-upload`
- 特征文件：`POST /v1/lodge/tasks/infer-from-feature-npy-upload`

查询任务：

```bat
curl "http://127.0.0.1:8002/v1/lodge/tasks/<task_id>"
```

下载接口：

```text
GET /v1/lodge/tasks/<task_id>/download
GET /v1/lodge/tasks/<task_id>/download-bvh
GET /v1/lodge/tasks/<task_id>/download-retarget
```

LODGE 任务输出保存在：

```text
LODGE_api/task_runs/<task_id>/
```

音频输入需要先提取特征并运行 LODGE 推理，耗时通常明显高于 InterGen 文本测试。需要快速验证 Blender/Rokoko 链路时，优先使用 InterGen。

## 前端环境变量

Vite 支持以下变量：

```text
VITE_API_HOST
VITE_API_PROTOCOL
VITE_INTERGEN_API_BASE
VITE_LODGE_API_BASE
VITE_LODGE_ROOT
VITE_LODGE_PYTHON_EXECUTABLE
VITE_LODGE_RETARGET_ENABLED
VITE_LODGE_BLENDER_EXE
VITE_LODGE_TARGET_FBX
VITE_LODGE_RETARGET_MAPPING
VITE_LODGE_RETARGET_SCRIPT
```

本地默认值：

```text
VITE_INTERGEN_API_BASE=http://127.0.0.1:8001
VITE_LODGE_API_BASE=http://127.0.0.1:8002
VITE_LODGE_ROOT=D:/HumanAction_Platform/LODGE-main
```

前端分辨率选项目前只影响界面状态，没有传给后端渲染参数。

## 关键重定向配置

当前启动 BAT 中最常调整的变量：

```bat
set "INTERGEN_BLENDER_EXE=D:\Blender_4.2\blender.exe"
set "INTERGEN_TARGET_FBX=D:\HumanAction_Platform\X Bot.fbx"
set "INTERGEN_RETARGET_MAPPING=D:\HumanAction_Platform\momask-main\assets\mapping.json"
set "INTERGEN_RETARGET_RENDER_SIZE=1080x1080"

set "LODGE_BLENDER_EXE=D:\Blender_4.2\blender.exe"
set "LODGE_TARGET_FBX=D:\HumanAction_Platform\X Bot.fbx"
set "LODGE_RETARGET_MAPPING=D:\HumanAction_Platform\momask-main\assets\mapping.json"
```

修改 BAT 后必须重启对应 API，正在运行的 Python 进程不会自动读取新配置。

## 常见问题

### 1. 中文提示词生成成了不相关动作

先查看任务返回的 `final_prompt`。如果仍然是中文、为空或与原文无关，检查 `DASHSCOPE_API_KEY` 和网络连接。复杂提示词还可能被模型训练数据覆盖不足限制。

### 2. 视频只有 4 秒左右

新任务应为 180～210 帧，即 6～7 秒。旧任务的 NPY/BVH 不会自动延长；重启 API 后重新提交文本。还可查看 `generated_frames`、`fps` 和 `duration_seconds`。

### 3. 已生成 BVH，但没有重定向视频

依次检查：

1. `*_bvh_report.json` 中的 `quality.passed`、`warnings` 和 `violations`。
2. `retarget_manifest.json` 中 Blender、FBX、mapping 和 BVH 路径。
3. `rokoko_retarget_report.json` 是否生成，以及 `status` 和 `retarget_pairs`。
4. Blender 中是否安装了 Rokoko 插件。

修复配置后可调用 `retry-retarget`，无需重新跑 InterGen。

### 4. Rokoko 日志提示找不到 `rokoko` 或 `rsl`

脚本会尝试多个候选插件模块名。只要报告中的 `enabled_addons` 包含实际 Rokoko 插件、两个 `retarget_pairs` 均返回 `FINISHED`，且报告状态为 `completed`，这些候选模块探测错误通常不影响结果。

### 5. 人物穿模或距离不合适

- 舞蹈可提高 `INTERGEN_RETARGET_DANCE_SPACING`。
- 拳击可调整 `INTERGEN_RETARGET_BOXING_SPACING`。
- 击剑可调整 `INTERGEN_RETARGET_FENCING_SPACING`。

间距是静态附加偏移，不能代替逐帧双人碰撞约束。若穿模来自原始动作，需要进一步增加人体间碰撞检测或重新选择候选。

### 6. 终端出现 `UnicodeDecodeError: gbk`

使用推荐 BAT 启动。脚本已经设置：

```bat
set "PYTHONIOENCODING=utf-8"
set "INTERGEN_SUBPROCESS_ENCODING=utf-8"
set "INTERGEN_SUBPROCESS_ERRORS=replace"
```

LODGE BAT 也有对应的 UTF-8 子进程设置。

### 7. API 重启后任务查询 404

任务状态保存在内存中。任务文件仍在 `task_runs/<task_id>/`；InterGen 历史任务可以直接调用 `retry-retarget` 重新注册并执行重定向，但普通状态查询不会自动恢复。

### 8. 端口已被占用

先关闭旧 API，或者在启动前指定其他端口：

```bat
set INTERGEN_PORT=8011
set LODGE_PORT=8012
```

## 子文档

- [InterGen API 说明](InterGen_api/README.md)
- [LODGE API 说明](LODGE_api/README.md)
- [前后端调用说明](project/BACKEND_CALL_GUIDE.md)

## 上游项目

- [InterGen](https://tr3e.github.io/intergen-page/)
- [LODGE](https://li-ronghui.github.io/lodge)

## 后续工作建议

- 增加 InterGen 重定向视频的独立下载接口，并统一前端字段名。
- 持久化任务状态，使 API 重启后仍可查询历史任务。
- 增加文本语义评分，而不仅依赖碰撞质量选择候选。
- 为球类、击剑等持道具动作增加训练数据和 Blender 道具绑定。
- 增加逐帧双人体表碰撞检测和距离约束。
- 支持两个不同 FBX 角色及独立骨骼映射。
