# HumanAction-Platform 人体运动生成平台
本项目是基于InterGen与lodge开源模型完成的多模态驱动的人体运动生成平台

## 1. 开源模型对应仓库链接
- InterGen模型：[点击查看InterGen模型](https://tr3e.github.io/intergen-page/)
- LODGE模型：[点击查看LODGE模型](https://li-ronghui.github.io/lodge)

## 2. 前端文件
- 前端文件采用vue语言编写，文档见 `project/BACKEND_CALL_GUIDE.md`
- 前端页面文件见 `project/src/App.vue`

## 3. 后端文件
- 后端文件为`intergen_async_api.py` 和 `lodge_async_api.py`
- 本地运行时请先启动两个api文件，再启动前端vue文件
