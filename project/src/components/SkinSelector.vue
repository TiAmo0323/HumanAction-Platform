<template>
  <section class="skin-selector" aria-labelledby="skin-selector-title">
    <div class="skin-selector-copy">
      <span class="skin-selector-kicker">角色外观</span>
      <div>
        <div class="skin-selector-heading">
          <h3 id="skin-selector-title">选择蒙皮</h3>
          <button
            type="button"
            class="selection-mode-toggle"
            :class="{ multi: isMultiSelect }"
            :aria-pressed="isMultiSelect"
            :aria-label="isMultiSelect ? '当前为多选模式，点击切换为单选模式' : '当前为单选模式，点击切换为多选模式'"
            :title="isMultiSelect ? '切换为单选模式' : '切换为多选模式'"
            :disabled="disabled"
            @click="toggleSelectionMode"
          >
            <span class="selection-mode-icon" aria-hidden="true">
              <i></i>
              <i></i>
            </span>
            {{ isMultiSelect ? '多选模式' : '单选模式' }}
          </button>
        </div>
        <p>{{ selectionHint }}</p>
      </div>
    </div>

    <div
      class="skin-options"
      role="group"
      :aria-label="isMultiSelect ? '蒙皮多选项' : '蒙皮单选项'"
    >
      <button
        v-for="option in options"
        :key="option.id"
        type="button"
        class="skin-option"
        :class="{ active: modelValue.includes(option.id), single: !isMultiSelect }"
        :aria-pressed="modelValue.includes(option.id)"
        :disabled="disabled"
        @click="toggleOption(option.id)"
      >
        <span class="skin-option-indicator" aria-hidden="true">
          <span></span>
        </span>
        <span class="skin-option-content">
          <span class="skin-option-heading">
            <strong>{{ option.label }}</strong>
            <small>{{ option.category }}</small>
          </span>
          <span class="skin-option-description">{{ option.description }}</span>
        </span>
      </button>

      <div class="skin-future-note" aria-label="更多蒙皮资源即将接入">
        <span class="skin-future-icon" aria-hidden="true">＋</span>
        <span>
          <strong>更多蒙皮</strong>
          <small>资源接入后将在这里显示</small>
        </span>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import {
  MULTI_SKIN_SELECTION,
  SINGLE_SKIN_SELECTION,
  normalizeSkinSelection,
  toggleSkinSelection
} from '../config/skinSelection'

const props = defineProps({
  modelValue: {
    type: Array,
    required: true
  },
  options: {
    type: Array,
    required: true
  },
  disabled: {
    type: Boolean,
    default: false
  },
  selectionMode: {
    type: String,
    default: SINGLE_SKIN_SELECTION,
    validator: (value) => [SINGLE_SKIN_SELECTION, MULTI_SKIN_SELECTION].includes(value)
  }
})

const emit = defineEmits(['update:modelValue', 'update:selectionMode'])

const isMultiSelect = computed(() => props.selectionMode === MULTI_SKIN_SELECTION)
const selectionHint = computed(() => (
  isMultiSelect.value
    ? '多选开启：可同时生成多个蒙皮视频。'
    : '单选开启：点击新蒙皮会替换当前选项。'
))

const toggleOption = (skinId) => {
  const next = toggleSkinSelection(props.modelValue, skinId, props.selectionMode)
  emit('update:modelValue', next)
}

const toggleSelectionMode = () => {
  const nextMode = isMultiSelect.value
    ? SINGLE_SKIN_SELECTION
    : MULTI_SKIN_SELECTION
  const nextSelection = normalizeSkinSelection(props.modelValue, nextMode)
  emit('update:selectionMode', nextMode)
  if (
    nextSelection.length !== props.modelValue.length
    || nextSelection.some((skinId, index) => skinId !== props.modelValue[index])
  ) {
    emit('update:modelValue', nextSelection)
  }
}
</script>

<style scoped>
.skin-selector {
  display: flex;
  align-items: center;
  gap: 18px;
  min-width: 0;
  padding: 9px 12px;
  border: 1px solid rgba(31, 143, 98, 0.2);
  border-radius: 16px;
  background: linear-gradient(120deg, rgba(236, 248, 241, 0.94), rgba(255, 250, 241, 0.9));
}

.skin-selector-copy {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 220px;
}

.skin-selector-kicker {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  border-radius: 13px;
  background: #1f8f62;
  color: #fff;
  font-size: 0.68rem;
  font-weight: 700;
  line-height: 1.05;
  text-align: center;
  box-shadow: 0 8px 18px rgba(31, 143, 98, 0.2);
}

.skin-selector-copy h3 {
  margin: 0;
  color: #213a2c;
  font-size: 0.94rem;
}

.skin-selector-heading {
  display: flex;
  align-items: center;
  gap: 8px;
}

.selection-mode-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 25px;
  padding: 4px 8px;
  border: 1px solid rgba(31, 143, 98, 0.28);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
  color: #416052;
  font-family: inherit;
  font-size: 0.65rem;
  font-weight: 700;
  cursor: pointer;
  transition: border-color 0.18s ease, background 0.18s ease, color 0.18s ease;
}

.selection-mode-toggle:hover:not(:disabled),
.selection-mode-toggle.multi {
  border-color: rgba(31, 143, 98, 0.58);
  background: rgba(31, 143, 98, 0.1);
  color: #18774f;
}

.selection-mode-toggle:focus-visible {
  outline: 3px solid rgba(31, 143, 98, 0.2);
  outline-offset: 2px;
}

.selection-mode-toggle:disabled {
  cursor: not-allowed;
  opacity: 0.62;
}

.selection-mode-icon {
  position: relative;
  width: 15px;
  height: 10px;
}

.selection-mode-icon i {
  position: absolute;
  top: 2px;
  width: 7px;
  height: 7px;
  border: 1.5px solid currentColor;
  border-radius: 50%;
  background: #fff;
}

.selection-mode-icon i:first-child {
  left: 0;
}

.selection-mode-icon i:last-child {
  right: 0;
  opacity: 0.35;
}

.selection-mode-toggle.multi .selection-mode-icon i:last-child {
  opacity: 1;
}

.skin-selector-copy p {
  margin: 2px 0 0;
  color: #68776e;
  font-size: 0.72rem;
  line-height: 1.35;
}

.skin-options {
  display: grid;
  grid-template-columns: repeat(3, minmax(150px, 1fr));
  gap: 8px;
  width: 100%;
  min-width: 0;
}

.skin-option,
.skin-future-note {
  min-width: 0;
  min-height: 54px;
  border-radius: 13px;
}

.skin-option {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 10px;
  border: 1px solid rgba(27, 72, 48, 0.14);
  background: rgba(255, 255, 255, 0.82);
  color: #213128;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.skin-option:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: rgba(31, 143, 98, 0.42);
}

.skin-option:focus-visible {
  outline: 3px solid rgba(31, 143, 98, 0.2);
  outline-offset: 2px;
}

.skin-option:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.skin-option.active {
  border-color: rgba(31, 143, 98, 0.68);
  background: #fff;
  box-shadow: 0 7px 16px rgba(31, 143, 98, 0.12), inset 0 0 0 1px rgba(31, 143, 98, 0.12);
}

.skin-option-indicator {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  flex: 0 0 18px;
  border: 1.5px solid #9aaba0;
  border-radius: 5px;
}

.skin-option.active .skin-option-indicator {
  border-color: #1f8f62;
}

.skin-option.single .skin-option-indicator,
.skin-option.single .skin-option-indicator span {
  border-radius: 50%;
}

.skin-option-indicator span {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  background: transparent;
}

.skin-option.active .skin-option-indicator span {
  background: #1f8f62;
}

.skin-option-content {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.skin-option-heading {
  display: flex;
  align-items: baseline;
  gap: 7px;
}

.skin-option-heading strong {
  font-size: 0.84rem;
}

.skin-option-heading small {
  color: #1f8f62;
  font-size: 0.64rem;
  font-weight: 700;
}

.skin-option-description {
  margin-top: 2px;
  overflow: hidden;
  color: #6b786f;
  font-size: 0.66rem;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skin-future-note {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 10px;
  border: 1px dashed rgba(87, 106, 94, 0.28);
  color: #718078;
}

.skin-future-icon {
  display: grid;
  place-items: center;
  width: 25px;
  height: 25px;
  flex: 0 0 25px;
  border-radius: 8px;
  background: rgba(71, 91, 78, 0.08);
  font-size: 1rem;
}

.skin-future-note > span:last-child {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.skin-future-note strong {
  font-size: 0.77rem;
}

.skin-future-note small {
  margin-top: 2px;
  overflow: hidden;
  font-size: 0.64rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 1100px) {
  .skin-selector {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }

  .skin-selector-copy {
    min-width: 0;
  }
}

@media (max-width: 720px) {
  .skin-options {
    grid-template-columns: 1fr;
  }
}
</style>
