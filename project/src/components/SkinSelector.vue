<template>
  <section class="skin-selector" aria-labelledby="skin-selector-title">
    <div class="skin-selector-copy">
      <span class="skin-selector-kicker">角色外观</span>
      <div>
        <h3 id="skin-selector-title">选择蒙皮</h3>
        <p>可选择一个或多个蒙皮；后端只生成勾选的视频。</p>
      </div>
    </div>

    <div class="skin-options" role="group" aria-label="蒙皮多选项">
      <button
        v-for="option in options"
        :key="option.id"
        type="button"
        class="skin-option"
        :class="{ active: modelValue.includes(option.id) }"
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
  }
})

const emit = defineEmits(['update:modelValue'])

const toggleOption = (skinId) => {
  const next = props.modelValue.includes(skinId)
    ? props.modelValue.filter((value) => value !== skinId)
    : [...props.modelValue, skinId]
  if (!next.length) return
  emit('update:modelValue', next)
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
