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

        <button class="new-chat">+ 新建对话</button>

        <nav class="history-list">
          <h2>最近会话</h2>
          <button v-for="item in history" :key="item.id" class="history-item">
            <span class="dot"></span>
            {{ item.title }}
          </button>
        </nav>
      </aside>

      <main class="chat-panel" @click="closeMenus">
        <header class="top-bar">
          <div class="model-chip">Model: SynicShade</div>
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
          <div class="stage-frame" aria-label="动画展示区"></div>
        </section>

        <section class="render-progress" aria-label="生成进度">
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: `${generationProgress}%` }"></div>
          </div>
          <span class="progress-value">{{ generationProgress }}%</span>
        </section>

        <form class="composer" @submit.prevent="sendMessage" @click.stop>
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
              v-model="prompt"
              rows="1"
              :placeholder="composerPlaceholder"
              @focus="activateTextMode"
              @keydown.enter.exact.prevent="sendMessage"
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
            <span></span>
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

          <input ref="uploadFileInput" class="hidden-input" type="file" accept="audio/*" @change="onUploadFileChange" />
        </form>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const prompt = ref('')
const isGenerating = ref(false)
const generationProgress = ref(0)
const resolution = ref('1080p')
const showResolutionMenu = ref(false)
const inputMode = ref('text')
const uploadFileInput = ref(null)
const selectedVoiceFile = ref('')
const selectedMusicFile = ref('')

const resolutions = [
  { label: '720p', value: '720p' },
  { label: '1080p', value: '1080p' },
  { label: '2K', value: '2k' }
]

const history = ref([
  { id: 1, title: 'Vue 项目结构优化建议' },
  { id: 2, title: '品牌介绍页文案草稿' },
  { id: 3, title: 'CSS 动效实现思路' }
])

const sendMessage = () => {
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
  generationProgress.value = 50

  prompt.value = ''

  setTimeout(() => {
    isGenerating.value = false
    generationProgress.value = 100
  }, 1400)
}

const composerPlaceholder = computed(() => {
  if (inputMode.value === 'voice') return '语音模式：可直接说话，或点击左侧 + 上传语音/音乐文件'
  if (inputMode.value === 'music') return '请上传音乐文件，系统将按节奏生成舞蹈'
  return '请输入舞蹈提示词，例如：国风双人舞，慢镜头，舞台追光'
})

const closeMenus = () => {
  showResolutionMenu.value = false
}

const activateTextMode = () => {
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

  if (inputMode.value === 'voice') {
    selectedVoiceFile.value = file.name
  } else {
    inputMode.value = 'music'
    selectedMusicFile.value = file.name
  }
}

const selectResolution = (value) => {
  resolution.value = value
  showResolutionMenu.value = false
}

const saveRender = async () => {
  const fileName = `scene-${resolution.value}.mp4`

  if (typeof window.showSaveFilePicker === 'function') {
    try {
      const handle = await window.showSaveFilePicker({
        suggestedName: fileName,
        types: [
          {
            description: 'MP4 Video',
            accept: { 'video/mp4': ['.mp4'] }
          }
        ]
      })
      const writable = await handle.createWritable()
      await writable.write('')
      await writable.close()
      return
    } catch {
      return
    }
  }

  const blob = new Blob([''], { type: 'video/mp4' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.click()
  URL.revokeObjectURL(url)
}
</script>
