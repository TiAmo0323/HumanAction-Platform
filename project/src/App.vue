<template>
  <div class="viewport-frame">
    <div class="page-shell">
      <div class="aurora aurora-a"></div>
      <div class="aurora aurora-b"></div>

      <aside class="side-panel">
        <div class="brand-block">
          <div class="logo-orb"></div>
          <div>
            <h1>Nova Chat</h1>
            <p>Built with Vue 3</p>
          </div>
        </div>

        <button type="button" class="new-chat" @click="startNewChat">+ 新建对话</button>

        <nav class="history-list">
          <h2>最近会话</h2>
          <div v-for="item in history" :key="item.id" class="history-item">
            <span class="dot"></span>
            <span class="history-title">{{ item.title }}</span>
            <button
              type="button"
              class="history-delete"
              aria-label="删除聊天记录"
              title="删除"
              @click.stop="removeHistoryItem(item.id)"
            >
              ×
            </button>
          </div>
        </nav>
      </aside>

      <main class="chat-panel" @click="closeMenus">
        <header class="top-bar">
          <div class="top-title-block">
            <div class="model-chip">Model: SynicShade</div>
            <h2 class="platform-title">“联觉动影”多模态人体运动动画生成平台</h2>
          </div>
          <div class="top-actions">
            <div class="menu-wrap" @click.stop>
              <button
                type="button"
                class="ghost-btn icon-only"
                aria-label="分辨率"
                :title="`分辨率：${resolution.toUpperCase()}`"
                @click="showResolutionMenu = !showResolutionMenu"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    d="M4 6h16v9H4zM7 20h10"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.8"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </button>

              <div v-if="showResolutionMenu" class="resolution-pop" role="menu" aria-label="选择分辨率">
                <button
                  v-for="item in resolutions"
                  :key="item.value"
                  type="button"
                  class="resolution-item"
                  :class="{ active: resolution === item.value }"
                  @click="selectResolution(item.value)"
                >
                  {{ item.label }}
                </button>
              </div>
            </div>

            <button class="ghost-btn">分享</button>
            <button class="ghost-btn">设置</button>
            <button type="button" class="ghost-btn icon-only" aria-label="保存" title="保存" @click="saveRender">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M12 4v10m0 0 4-4m-4 4-4-4M5 19h14"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.8"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </button>
          </div>
        </header>

        <section class="generation-stage" :class="{ generating: isGenerating }">
          <div class="stage-frame" aria-label="动画展示区">
            <video
              v-if="generatedVideoUrl"
              ref="generatedVideoRef"
              class="result-video"
              :src="generatedVideoUrl"
              controls
              playsinline
              preload="metadata"
            ></video>
          </div>
        </section>

        <section class="render-progress" aria-label="生成进度">
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: `${generationProgress}%` }"></div>
          </div>
          <span class="progress-value">{{ generationProgress }}%</span>
        </section>
        <p class="task-status" v-if="taskStatusText">{{ taskStatusText }}</p>
        <div class="video-actions" v-if="generatedVideoUrl">
          <button type="button" class="ghost-btn" @click="openVideoInNewTab">打开播放页</button>
          <button type="button" class="ghost-btn" @click="downloadGeneratedVideo">下载视频</button>
          <button type="button" class="ghost-btn" @click="openVideoFolder">打开视频所在文件夹</button>
          <button type="button" class="ghost-btn" @click="copyVideoPath">复制后端保存路径</button>
        </div>

        <form class="composer" @submit.prevent="sendMessage" @keydown.enter.exact.prevent="handleComposerEnter" @click.stop>
          <div class="composer-input-row">
            <button type="button" class="edge-btn" aria-label="上传文件" title="上传文件" @click="triggerFileUpload">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M12 5v14M5 12h14"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.8"
                  stroke-linecap="round"
                />
              </svg>
            </button>

            <textarea
              ref="composerTextarea"
              v-model="prompt"
              rows="1"
              :placeholder="composerPlaceholder"
              @focus="activateTextMode"
              @keydown.enter.exact.prevent.stop="handleComposerEnter"
            ></textarea>

            <button type="button" class="edge-btn" aria-label="语音输入" title="语音输入" @click="startVoiceInput">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M12 4a3 3 0 0 0-3 3v4a3 3 0 0 0 6 0V7a3 3 0 0 0-3-3Zm-6 7a6 6 0 0 0 12 0M12 17v3M9 20h6"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.8"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </button>
          </div>

          <div class="composer-footer">
            <span class="upload-status" :class="{ ready: isUploadReady }">{{ uploadStatus }}</span>
            <button type="submit" class="send-fab" aria-label="生成舞蹈" title="生成舞蹈">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M6 12h12m-5-5 5 5-5 5"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </button>
          </div>

          <input
            ref="uploadFileInput"
            class="hidden-input"
            type="file"
            accept=".mp4,.MP4,.mp3,.MP3,.npy,.NPY,.wav,.WAV"
            @change="onUploadFileChange"
          />
        </form>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import axios from 'axios'

const intergenApiBase = (import.meta.env.VITE_INTERGEN_API_BASE || 'http://127.0.0.1:8001').replace(/\/$/, '')
const lodgeApiBase = (import.meta.env.VITE_LODGE_API_BASE || 'http://127.0.0.1:8002').replace(/\/$/, '')
const lodgeRoot = (import.meta.env.VITE_LODGE_ROOT || 'D:/HumanAction_Platform/LODGE-main').trim()
const lodgePythonExecutable = (import.meta.env.VITE_LODGE_PYTHON_EXECUTABLE || '').trim()

const prompt = ref('')
const isGenerating = ref(false)
const generationProgress = ref(0)
const resolution = ref('1080p')
const showResolutionMenu = ref(false)
const inputMode = ref('text')
const uploadFileInput = ref(null)
const composerTextarea = ref(null)
const selectedVoiceFile = ref('')
const selectedMusicFile = ref('')
const selectedMusicFileObj = ref(null)
const generatedVideoRef = ref(null)
const uploadStatus = ref('')
const isUploadReady = ref(false)
const taskStatusText = ref('')

const generatedVideoUrl = ref('')
const generatedVideoDownloadUrl = ref('')
const generatedVideoFilePath = ref('')
const generatedTaskId = ref('')
const generatedTaskBaseUrl = ref('')
const allowedUploadExts = new Set(['mp4', 'mp3', 'npy', 'wav'])
const audioUploadExts = new Set(['mp4', 'mp3', 'wav'])

const resolutions = [
  { label: '720p', value: '720p' },
  { label: '1080p', value: '1080p' },
  { label: '2K', value: '2k' }
]

const history = ref([])

const addHistoryItem = (title) => {
  history.value.unshift({
    id: Date.now(),
    title: title
  })
}

const removeHistoryItem = (id) => {
  history.value = history.value.filter((item) => item.id !== id)
}

const startNewChat = () => {
  if (window.pollTimer) {
    clearInterval(window.pollTimer)
    window.pollTimer = null
  }

  prompt.value = ''
  isGenerating.value = false
  generationProgress.value = 0
  inputMode.value = 'text'
  selectedVoiceFile.value = ''
  selectedMusicFile.value = ''
  selectedMusicFileObj.value = null
  generatedVideoUrl.value = ''
  generatedVideoDownloadUrl.value = ''
  generatedVideoFilePath.value = ''
  generatedTaskId.value = ''
  generatedTaskBaseUrl.value = ''
  uploadStatus.value = ''
  isUploadReady.value = false
  taskStatusText.value = ''

  addHistoryItem('新建对话')
}

const sendMessage = async () => {
  if (inputMode.value === 'text' && !prompt.value.trim()) {
    window.alert('请先输入舞蹈描述文本，再点击生成。')
    return
  }

  if (inputMode.value === 'voice' && !selectedVoiceFile.value) {
    window.alert('请先上传语音文件，或点击语音图标选择语音输入。')
    return
  }

  if (inputMode.value === 'music' && !selectedMusicFile.value) {
    window.alert('请先上传音乐文件，再点击生成。')
    return
  }

  isGenerating.value = true
  isUploadReady.value = false
  generationProgress.value = 10
  taskStatusText.value = '任务已提交，等待后端开始处理...'
  const currentPrompt = prompt.value
  prompt.value = ''

  try {
    let apiUrl = ''
    let payload = {}
    
    if (inputMode.value === 'text') {
      apiUrl = `${intergenApiBase}/v1/intergen/tasks/generate`
      payload = { text: currentPrompt }
      addHistoryItem(`文本驱动: ${currentPrompt}`)
    } 
    else if (inputMode.value === 'music') {
      if (!selectedMusicFileObj.value) {
        window.alert('未检测到可上传的音乐文件对象，请重新选择文件。')
        isGenerating.value = false
        return
      }

      const fileObj = selectedMusicFileObj.value
      const ext = (fileObj.name.split('.').pop() || '').toLowerCase()
      const musicId = fileObj.name.split('.').slice(0, -1).join('.') || fileObj.name
      if (!lodgeRoot) {
        window.alert('未配置 LODGE 根目录，请在前端环境变量中设置 VITE_LODGE_ROOT。')
        isGenerating.value = false
        generationProgress.value = 0
        return
      }
      const formData = new FormData()
      formData.append('lodge_root', lodgeRoot)
      formData.append('song_id', musicId)
      formData.append('mode', 'smplx')
      formData.append('device', '0')
      formData.append('fps', '30')
      if (lodgePythonExecutable) {
        formData.append('python_executable', lodgePythonExecutable)
      }

      if (ext === 'npy') {
        apiUrl = `${lodgeApiBase}/v1/lodge/tasks/infer-from-feature-npy-upload`
        formData.append('npy_file', fileObj)
      } else {
        apiUrl = `${lodgeApiBase}/v1/lodge/tasks/infer-from-audio-upload`
        formData.append('audio_file', fileObj)
      }

      payload = formData
      addHistoryItem(`音乐驱动 (编号): ${musicId}`)
    } 
    else if (inputMode.value === 'voice') {
      window.alert('语音功能暂未开放，请尝试文字或音乐输入。')
      isGenerating.value = false
      return
    }
    
    const axiosConfig = payload instanceof FormData
      ? { headers: { 'Content-Type': 'multipart/form-data' } }
      : undefined

    const res = await axios.post(apiUrl, payload, axiosConfig)
    const taskId = res.data.task_id
    console.log("任务已提交，ID:", taskId)

    const baseUrl = apiUrl.substring(0, apiUrl.lastIndexOf('/tasks') + 6)

    // 启动轮询：因为 8001/8002 都是异步生成，需要不断问“好了没”
    startPolling(taskId, baseUrl)


  } catch (error) {
    console.error("请求出错了:", error)
    window.alert('连接服务器失败，可能未开机或 IP 错误')
    generationProgress.value = 0
    isGenerating.value = false
  }
}

const handleComposerEnter = () => {
  if (isGenerating.value) return
  sendMessage()
}

const startPolling = (taskId, baseUrl) => {
  // 清除可能存在的旧定时器
  if (window.pollTimer) clearInterval(window.pollTimer)

  window.pollTimer = setInterval(async () => {
    try {
      const checkRes = await axios.get(`${baseUrl}/${taskId}`)
      const task = checkRes.data
      taskStatusText.value = task.message || `任务状态：${task.status}`

      if (typeof task.progress === 'number') {
        generationProgress.value = Math.max(0, Math.min(100, task.progress))
      } else if (generationProgress.value < 95) {
        // 兼容旧后端：没有 progress 字段时保持原先的模拟进度。
        generationProgress.value += 5
      }

      if (task.status === 'succeeded') {
        clearInterval(window.pollTimer)
        window.pollTimer = null
        generationProgress.value = 100
        isGenerating.value = false
        taskStatusText.value = '任务已完成，视频可播放或下载。'

        // 设置生成的视频地址 (供页面上的 <video> 标签使用)
        generatedVideoUrl.value = `${baseUrl}/${taskId}/download`
        generatedVideoDownloadUrl.value = `${baseUrl}/${taskId}/download?as_attachment=true`
        generatedVideoFilePath.value = task.output_mp4_path || ''
        generatedTaskId.value = taskId
        generatedTaskBaseUrl.value = baseUrl

        console.log("生成成功！视频地址：", generatedVideoUrl.value)

        const shouldOpenPlayer = window.confirm('视频已生成完毕。点击“确定”将直接调用系统默认 MP4 播放器播放；点击“取消”进入下载选项。')
        if (shouldOpenPlayer) {
          await openVideoWithSystemPlayer()
        } else {
          const shouldDownload = window.confirm('是否立即下载该视频？')
          if (shouldDownload) {
            downloadGeneratedVideo()
          } else {
            await openVideoFolder()
            window.alert('已尝试打开视频所在文件夹。你可以继续使用页面上的“下载视频/复制后端保存路径”按钮。')
          }
        }
      } 
      else if (task.status === 'failed') {
        clearInterval(window.pollTimer)
        window.pollTimer = null
        isGenerating.value = false
        generationProgress.value = 0
        taskStatusText.value = '任务失败，请查看错误信息。'
        window.alert('生成失败: ' + (task.message || '未知错误'))
      }
    } catch (err) {
      console.error("轮询任务状态失败:", err)
      if (err?.response?.status === 404) {
        clearInterval(window.pollTimer)
        window.pollTimer = null
        isGenerating.value = false
        generationProgress.value = 0
        taskStatusText.value = '任务不存在（后端重启后旧任务会失效），请重新提交。'
        window.alert('任务不存在（可能是后端重启导致），请重新上传并提交。')
      }
    }
  }, 5000) // 每 5 秒查询一次
}


const composerPlaceholder = computed(() => {
  if (inputMode.value === 'voice') return '语音模式：可直接说话，或点击左侧 + 上传语音/音乐文件'
  if (inputMode.value === 'music') return '请上传音乐文件，系统将按节奏生成舞蹈'
  return '请输入舞蹈提示词，例如：两个人正在跳舞。'
})

const closeMenus = () => {
  showResolutionMenu.value = false
}

const activateTextMode = () => {
  if (selectedMusicFileObj.value) return
  inputMode.value = 'text'
}

const startVoiceInput = () => {
  inputMode.value = 'voice'
}

const triggerFileUpload = () => {
  uploadFileInput.value?.click()
}

const onUploadFileChange = (event) => {
  const file = event.target.files?.[0]
  if (!file) return

  const ext = (file.name.split('.').pop() || '').toLowerCase()
  if (!allowedUploadExts.has(ext)) {
    window.alert('仅支持上传 mp4、mp3、npy 或 wav 文件。')
    event.target.value = ''
    return
  }

  // 上传文件后统一走 LODGE 音乐流程，避免误留在 voice 模式导致无法提交。
  inputMode.value = 'music'
  selectedMusicFile.value = file.name
  selectedMusicFileObj.value = file

  if (audioUploadExts.has(ext)) {
    uploadStatus.value = `音频上传成功：${file.name}。按回车可调用 LODGE 模型。`
  } else {
    uploadStatus.value = `文件上传成功：${file.name}。按回车可开始生成。`
  }
  isUploadReady.value = true
  selectedVoiceFile.value = ''

  nextTick(() => {
    composerTextarea.value?.focus()
  })

  event.target.value = ''
}

const selectResolution = (value) => {
  resolution.value = value
  showResolutionMenu.value = false
}

const openVideoInNewTab = () => {
  if (!generatedVideoUrl.value) {
    window.alert('当前没有可播放的视频。')
    return
  }
  window.open(generatedVideoUrl.value, '_blank', 'noopener,noreferrer')
}

const openVideoWithSystemPlayer = async () => {
  if (!generatedTaskId.value || !generatedTaskBaseUrl.value) {
    window.alert('当前没有可播放的视频任务。')
    return
  }

  try {
    await axios.post(`${generatedTaskBaseUrl.value}/${generatedTaskId.value}/open-output-player`)
  } catch (err) {
    console.error('调用系统播放器失败:', err)
    window.alert('调用系统播放器失败，将为你打开网页播放页作为备用方案。')
    openVideoInNewTab()
  }
}

const downloadGeneratedVideo = () => {
  const downloadUrl = generatedVideoDownloadUrl.value || generatedVideoUrl.value
  if (!downloadUrl) {
    window.alert('当前没有可下载的视频。')
    return
  }
  const link = document.createElement('a')
  link.href = downloadUrl
  link.target = '_blank'
  link.rel = 'noopener noreferrer'
  link.click()
}

const copyVideoPath = async () => {
  if (!generatedVideoFilePath.value) {
    window.alert('后端未返回视频保存路径。')
    return
  }
  try {
    await navigator.clipboard.writeText(generatedVideoFilePath.value)
    window.alert('已复制视频保存路径。')
  } catch {
    window.alert(`复制失败，请手动复制：${generatedVideoFilePath.value}`)
  }
}

const openVideoFolder = async () => {
  if (!generatedTaskId.value || !generatedTaskBaseUrl.value) {
    window.alert('当前没有可定位的视频任务。')
    return
  }

  try {
    await axios.post(`${generatedTaskBaseUrl.value}/${generatedTaskId.value}/open-output-folder`)
  } catch (err) {
    console.error('打开视频文件夹失败:', err)
    if (generatedVideoFilePath.value) {
      window.alert(`自动打开失败，请手动打开该路径：${generatedVideoFilePath.value}`)
    } else {
      window.alert('打开视频文件夹失败，请稍后重试。')
    }
  }
}

const saveRender = async () => {
  downloadGeneratedVideo()
}
</script>

<style scoped>
.video-actions {
  display: flex;
  gap: 10px;
  margin: 8px 0 14px;
  flex-wrap: wrap;
}
</style>
