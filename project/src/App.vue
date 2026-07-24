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

        <SkinSelector
          :model-value="selectedSkinIds"
          :options="skinOptions"
          :disabled="isGenerating"
          @update:model-value="selectSkins"
        />

        <section class="generation-stage" :class="{ generating: isGenerating }">
          <div class="stage-frame" aria-label="动画展示区">
            <div class="stage-skin-badge">
              <span></span>
              {{ displayedSkinOption.label }} 蒙皮
            </div>
            <video
              v-if="generatedVideoUrl"
              ref="generatedVideoRef"
              class="result-video"
              :src="generatedVideoUrl"
              controls
              playsinline
              preload="metadata"
            ></video>
            <div v-else class="stage-empty-state">
              <span class="stage-empty-orb"></span>
              <strong>等待生成 {{ selectedSkinSummary }} 动画</strong>
              <small>输入文本或上传音频后开始生成</small>
            </div>
          </div>
        </section>

        <section class="render-progress" aria-label="生成进度">
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: `${generationProgress}%` }"></div>
          </div>
          <span class="progress-value">{{ generationProgress }}%</span>
        </section>
        <p class="task-status" v-if="taskStatusText">{{ taskStatusText }}</p>
        <p class="skin-result-notice" v-if="skinResultNotice">{{ skinResultNotice }}</p>
        <div v-if="generatedAvailableSkinIds.length > 1" class="result-skin-switch" aria-label="切换已生成的蒙皮视频">
          <span>查看结果：</span>
          <button
            v-for="skinId in generatedAvailableSkinIds"
            :key="skinId"
            type="button"
            class="ghost-btn"
            :class="{ active: generatedSkinId === skinId }"
            @click="applyGeneratedSkin(skinId)"
          >
            {{ resolveSkinOption(skinId).label }}
          </button>
        </div>
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
import { computed, nextTick, onMounted, ref } from 'vue'
import axios from 'axios'
import SkinSelector from './components/SkinSelector.vue'
import {
  DEFAULT_SKIN_ID,
  getSkinOption,
  skinOptions as defaultSkinOptions
} from './config/skinOptions'

const runtimeHost = (import.meta.env.VITE_API_HOST || (typeof window !== 'undefined' ? window.location.hostname : '47.116.49.93') || '47.116.49.93').trim()
const runtimeProtocol = (import.meta.env.VITE_API_PROTOCOL || (typeof window !== 'undefined' ? window.location.protocol.replace(':', '') : 'http') || 'http').trim().toLowerCase()
const apiProtocol = runtimeProtocol === 'https' ? 'https' : 'http'

const intergenApiBase = (import.meta.env.VITE_INTERGEN_API_BASE || `${apiProtocol}://${runtimeHost}:8001`).replace(/\/$/, '')
const lodgeApiBase = (import.meta.env.VITE_LODGE_API_BASE || `${apiProtocol}://${runtimeHost}:8002`).replace(/\/$/, '')
const lodgeRoot = (import.meta.env.VITE_LODGE_ROOT || 'D:/HumanAction_Platform/LODGE-main').trim()
const lodgePythonExecutable = (import.meta.env.VITE_LODGE_PYTHON_EXECUTABLE || '').trim()
const lodgeBlenderExecutable = (import.meta.env.VITE_LODGE_BLENDER_EXE || '').trim()
const lodgeTargetFbx = (import.meta.env.VITE_LODGE_TARGET_FBX || '').trim()
const lodgeRetargetMapping = (import.meta.env.VITE_LODGE_RETARGET_MAPPING || '').trim()
const lodgeRetargetScript = (import.meta.env.VITE_LODGE_RETARGET_SCRIPT || '').trim()

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
const skinOptions = ref([...defaultSkinOptions])
const selectedSkinIds = ref([DEFAULT_SKIN_ID])
const activeTaskSkinIds = ref([])
const generatedSkinId = ref('')
const generatedOutputs = ref({})
const skinResultNotice = ref('')

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

const resolveSkinOption = (skinId) => getSkinOption(skinId, skinOptions.value)
const skinLabels = (skinIds) => skinIds.map((skinId) => resolveSkinOption(skinId).label).join(' + ')
const selectedSkinSummary = computed(() => skinLabels(selectedSkinIds.value))
const displayedSkinOption = computed(() => resolveSkinOption(generatedSkinId.value || selectedSkinIds.value[0]))
const generatedAvailableSkinIds = computed(() =>
  Object.entries(generatedOutputs.value)
    .filter(([, output]) => output?.available)
    .map(([skinId]) => skinId)
)

const history = ref([])

const loadBackendSkinCatalog = async () => {
  const results = await Promise.allSettled([
    axios.get(`${intergenApiBase}/v1/intergen/skins`),
    axios.get(`${lodgeApiBase}/v1/lodge/skins`)
  ])
  const catalog = results
    .filter((result) => result.status === 'fulfilled')
    .map((result) => result.value.data)
    .find((payload) => Array.isArray(payload?.skins) && payload.skins.length)

  if (!catalog) return

  skinOptions.value = catalog.skins.map((skin) => ({
    id: skin.id,
    label: skin.label || skin.id,
    category: skin.category || '角色蒙皮',
    description: skin.description || '',
    outputKind: skin.output_kind,
    backendMode: skin.backend_mode || 'smplx'
  }))

  selectedSkinIds.value = selectedSkinIds.value.filter((skinId) =>
    skinOptions.value.some((skin) => skin.id === skinId)
  )
  if (!selectedSkinIds.value.length) {
    selectedSkinIds.value = [catalog.default_skin_id || DEFAULT_SKIN_ID]
  }
}

onMounted(() => {
  loadBackendSkinCatalog()
})

const applyGeneratedSkin = (skinId, updateStatus = true) => {
  const skin = resolveSkinOption(skinId)
  const output = generatedOutputs.value[skin.id]
  if (!output?.available) {
    return false
  }

  generatedVideoUrl.value = output.url
  generatedVideoDownloadUrl.value = output.downloadUrl || output.url
  generatedVideoFilePath.value = output.filePath || ''
  generatedSkinId.value = skin.id
  skinResultNotice.value = `当前展示：${skin.label} 蒙皮。你可以直接切换其他已生成的蒙皮结果。`
  if (updateStatus) {
    taskStatusText.value = `已切换到 ${skin.label} 蒙皮结果。`
  }
  return true
}

const selectSkins = (skinIds) => {
  const previousIds = selectedSkinIds.value
  selectedSkinIds.value = [...skinIds]
  if (isGenerating.value || !generatedTaskId.value) {
    skinResultNotice.value = isGenerating.value
      ? `任务生成期间已锁定为 ${skinLabels(activeTaskSkinIds.value)}。`
      : ''
    return
  }

  const addedSkinId = skinIds.find((skinId) => !previousIds.includes(skinId))
  const displaySkinId = addedSkinId || skinIds.find((skinId) => generatedOutputs.value[skinId]?.available)
  if (displaySkinId && !applyGeneratedSkin(displaySkinId)) {
    const skin = resolveSkinOption(displaySkinId)
    const output = generatedOutputs.value[displaySkinId]
    skinResultNotice.value = output?.reason || `${skin.label} 未在当前任务中生成，请重新提交任务。`
  }
}

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
  activeTaskSkinIds.value = []
  generatedSkinId.value = ''
  generatedOutputs.value = {}
  skinResultNotice.value = ''
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
  const requestedSkinIds = [...selectedSkinIds.value]
  const requestedSkins = requestedSkinIds.map(resolveSkinOption)
  const requestedSkin = requestedSkins[0]
  const requestedSkinSummary = skinLabels(requestedSkinIds)
  const requestsRetarget = requestedSkins.some((skin) => skin.outputKind === 'retarget')
  activeTaskSkinIds.value = requestedSkinIds
  skinResultNotice.value = `本次任务只生成：${requestedSkinSummary}`
  prompt.value = ''

  try {
    let apiUrl = ''
    let payload = {}
    
    if (inputMode.value === 'text') {
      apiUrl = `${intergenApiBase}/v1/intergen/tasks/generate`
      payload = {
        text: currentPrompt,
        skin_ids: requestedSkinIds,
        skin_id: requestedSkin.id,
        retarget_enabled: requestsRetarget
      }
      addHistoryItem(`文本驱动 · ${requestedSkinSummary}: ${currentPrompt}`)
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
      formData.append('mode', requestedSkin.backendMode)
      formData.append('device', '0')
      formData.append('fps', '30')
      requestedSkinIds.forEach((skinId) => formData.append('skin_ids', skinId))
      formData.append('skin_id', requestedSkin.id)
      formData.append('retarget_enabled', requestsRetarget ? 'true' : 'false')
      if (lodgePythonExecutable) {
        formData.append('python_executable', lodgePythonExecutable)
      }
      if (lodgeBlenderExecutable) {
        formData.append('blender_executable', lodgeBlenderExecutable)
      }
      if (lodgeTargetFbx) {
        formData.append('target_fbx', lodgeTargetFbx)
      }
      if (lodgeRetargetMapping) {
        formData.append('mapping_file', lodgeRetargetMapping)
      }
      if (lodgeRetargetScript) {
        formData.append('retarget_script', lodgeRetargetScript)
      }

      if (ext === 'npy') {
        apiUrl = `${lodgeApiBase}/v1/lodge/tasks/infer-from-feature-npy-upload`
        formData.append('npy_file', fileObj)
      } else {
        apiUrl = `${lodgeApiBase}/v1/lodge/tasks/infer-from-audio-upload`
        formData.append('audio_file', fileObj)
      }

      payload = formData
      addHistoryItem(`音乐驱动 · ${requestedSkinSummary}: ${musicId}`)
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
    startPolling(taskId, baseUrl, requestedSkinIds)


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

const startPolling = (taskId, baseUrl, requestedSkinIds) => {
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
        const requestedSummary = skinLabels(requestedSkinIds)
        taskStatusText.value = `任务已完成，已按选择生成：${requestedSummary}。`

        const retargetPath = task.output_retarget_mp4_path || task.output_retarget_path || ''
        const retargetSucceeded = task.retarget_status === 'succeeded' && Boolean(retargetPath)
        const taskRequestedSkinIds = task.requested_skin_ids?.length
          ? task.requested_skin_ids
          : requestedSkinIds
        const taskSkinId = task.skin_id || taskRequestedSkinIds[0]
        const retargetSkinId = (task.available_skin_ids || []).find((skinId) => skinId !== 'smpl')
          || (taskSkinId !== 'smpl' ? taskSkinId : 'robot')
        const outputs = {}
        if (task.output_mp4_path) {
          outputs.smpl = {
            available: Boolean(task.output_mp4_path),
            url: `${baseUrl}/${taskId}/download`,
            downloadUrl: `${baseUrl}/${taskId}/download?as_attachment=true`,
            filePath: task.output_mp4_path || ''
          }
        }
        if (retargetSucceeded) {
          outputs[retargetSkinId] = {
            available: retargetSucceeded,
            generated: retargetSucceeded,
            url: `${baseUrl}/${taskId}/download-retarget`,
            downloadUrl: `${baseUrl}/${taskId}/download-retarget?as_attachment=true`,
            filePath: retargetPath,
            reason: '本次任务没有生成可播放的机器人重定向视频。'
          }
        }
        taskRequestedSkinIds.forEach((skinId) => {
          if (!outputs[skinId]) {
            outputs[skinId] = {
              available: false,
              reason: `${resolveSkinOption(skinId).label} 未成功生成。`
            }
          }
        })
        generatedOutputs.value = outputs
        generatedTaskId.value = taskId
        generatedTaskBaseUrl.value = baseUrl
        const initialSkinId = requestedSkinIds.find((skinId) => outputs[skinId]?.available)
        if (initialSkinId) {
          applyGeneratedSkin(initialSkinId, false)
          const missingSkinIds = requestedSkinIds.filter((skinId) => !outputs[skinId]?.available)
          if (missingSkinIds.length) {
            skinResultNotice.value = `当前展示：${resolveSkinOption(initialSkinId).label}；未成功生成：${skinLabels(missingSkinIds)}。`
            taskStatusText.value = '任务部分完成，请查看未成功生成的蒙皮状态。'
          }
        } else {
          generatedVideoUrl.value = ''
          generatedVideoDownloadUrl.value = ''
          generatedVideoFilePath.value = ''
          skinResultNotice.value = '后端没有返回任何已选择蒙皮的可播放视频。'
          taskStatusText.value = '任务结束，但所选蒙皮均未成功生成。'
        }

        console.log("生成成功！视频地址：", generatedVideoUrl.value)
        if (!generatedVideoUrl.value) {
          window.alert('任务结束，但所选蒙皮没有生成可播放视频，请查看任务状态信息。')
          return
        }

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
    await axios.post(
      `${generatedTaskBaseUrl.value}/${generatedTaskId.value}/open-output-player`,
      null,
      { params: { skin_id: generatedSkinId.value || selectedSkinIds.value[0] } }
    )
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
    await axios.post(
      `${generatedTaskBaseUrl.value}/${generatedTaskId.value}/open-output-folder`,
      null,
      { params: { skin_id: generatedSkinId.value || selectedSkinIds.value[0] } }
    )
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

.result-skin-switch {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0 4px;
  color: #66736b;
  font-size: 0.78rem;
}

.result-skin-switch .ghost-btn.active {
  border-color: rgba(31, 143, 98, 0.58);
  background: rgba(31, 143, 98, 0.1);
  color: #176d4b;
}

.stage-skin-badge {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 6px 10px;
  border: 1px solid rgba(255, 255, 255, 0.5);
  border-radius: 999px;
  background: rgba(18, 37, 26, 0.7);
  color: #fff;
  font-size: 0.74rem;
  font-weight: 700;
  backdrop-filter: blur(8px);
}

.stage-skin-badge span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #67dda5;
  box-shadow: 0 0 0 3px rgba(103, 221, 165, 0.18);
}

.stage-empty-state {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  justify-items: center;
  color: #53675a;
  text-align: center;
}

.stage-empty-state strong {
  margin-top: 12px;
  font-size: 0.92rem;
}

.stage-empty-state small {
  margin-top: 4px;
  color: #7a8a80;
  font-size: 0.74rem;
}

.stage-empty-orb {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, #fff 0 12%, #7fd2ae 20%, #1f8f62 68%, #176645 100%);
  box-shadow: 0 12px 26px rgba(31, 143, 98, 0.24);
}

.skin-result-notice {
  margin: -2px 2px 2px;
  color: #1f7955;
  font-size: 0.78rem;
  font-weight: 600;
}
</style>
