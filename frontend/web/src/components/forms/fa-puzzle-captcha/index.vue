<!-- 滑块拼图验证码：拖动图块补齐背景缺口，位置由服务端校验 -->
<template>
  <div class="fa-puzzle" :class="{ 'is-passed': passed, 'is-loading': loading }">
    <div class="fa-puzzle__reveal" :class="{ 'is-open': showImage }">
      <div class="fa-puzzle__reveal-inner">
        <div ref="areaRef" class="fa-puzzle__area">
          <img v-if="bgImage" :src="bgImage" class="fa-puzzle__bg" alt="" draggable="false" />
          <img
            v-if="pieceImage"
            :src="pieceImage"
            class="fa-puzzle__piece"
            alt=""
            draggable="false"
            :style="{ left: `${leftPx}px`, top: `${topPx}px`, width: `${pieceWidthPx}px` }"
          />
          <button
            v-if="!loading"
            type="button"
            class="fa-puzzle__refresh"
            :aria-label="refreshText"
            @click="$emit('refresh')"
          >
            <FaSvgIcon icon="ri:refresh-line" />
          </button>
          <div v-if="loading" class="fa-puzzle__mask">
            <FaSvgIcon icon="ri:loader-4-line" class="animate-spin" />
          </div>
        </div>
      </div>
    </div>

    <div
      ref="trackRef"
      class="fa-puzzle__track"
      :class="{ 'is-dragging': dragging }"
      @pointerdown.prevent="onPointerDown"
    >
      <div class="fa-puzzle__fill" :style="{ width: `${progress * 100}%` }" />
      <div class="fa-puzzle__handler" :style="{ transform: `translateX(${handlerLeft}px)` }">
        <FaSvgIcon :icon="passed ? 'ri:check-line' : 'ri:arrow-right-line'" />
      </div>
      <span class="fa-puzzle__text">{{ passed ? successText : text }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useElementSize } from "@vueuse/core";

defineOptions({ name: "FaPuzzleCaptcha" });

interface Props {
  bgImage: string;
  pieceImage: string;
  pieceY?: number;
  pieceWidth?: number;
  pieceHeight?: number;
  bgWidth?: number;
  bgHeight?: number;
  passed?: boolean;
  loading?: boolean;
  text: string;
  successText: string;
  refreshText: string;
}

const props = withDefaults(defineProps<Props>(), {
  pieceY: 0,
  pieceWidth: 55,
  pieceHeight: 48,
  bgWidth: 320,
  bgHeight: 160,
  passed: false,
  loading: false,
});

const emit = defineEmits<{
  verify: [position: number];
  refresh: [];
}>();

const areaRef = ref<HTMLElement>();
const trackRef = ref<HTMLElement>();
const { width: areaWidth, height: areaHeight } = useElementSize(areaRef);
const { width: trackWidth } = useElementSize(trackRef);

const progress = ref(0);
const dragging = ref(false);
const showImage = ref(false);
let hideTimer: number | undefined;
const startX = ref(0);
const startProgress = ref(0);

watch(
  () => props.bgImage,
  () => {
    progress.value = 0;
    dragging.value = false;
    showImage.value = false;
  }
);

const HANDLER = 40;

const pieceWidthPx = computed(
  () => (areaWidth.value || props.bgWidth) * (props.pieceWidth / props.bgWidth)
);
const leftPx = computed(
  () => progress.value * Math.max(0, (areaWidth.value || props.bgWidth) - pieceWidthPx.value)
);
const topPx = computed(
  () => (areaHeight.value || props.bgHeight) * (props.pieceY / props.bgHeight)
);
const handlerLeft = computed(
  () => progress.value * Math.max(0, (trackWidth.value || 300) - HANDLER)
);

function clampProgress(value: number): number {
  return Math.min(1, Math.max(0, value));
}

function onPointerDown(event: PointerEvent): void {
  if (props.passed || props.loading) return;
  dragging.value = true;
  showImage.value = true;
  if (hideTimer) window.clearTimeout(hideTimer);
  startX.value = event.clientX;
  startProgress.value = progress.value;
  (event.target as HTMLElement | null)?.setPointerCapture?.(event.pointerId);
  window.addEventListener("pointermove", onPointerMove);
  window.addEventListener("pointerup", onPointerUp, { once: true });
}

function onPointerMove(event: PointerEvent): void {
  if (!dragging.value) return;
  const rect = trackRef.value?.getBoundingClientRect();
  if (!rect) return;
  const delta = (event.clientX - startX.value) / Math.max(1, rect.width - HANDLER);
  progress.value = clampProgress(startProgress.value + delta);
}

function onPointerUp(): void {
  window.removeEventListener("pointermove", onPointerMove);
  dragging.value = false;
  if (progress.value <= 0.03) {
    progress.value = 0;
    showImage.value = false;
    return;
  }
  const max = Math.max(0, props.bgWidth - props.pieceWidth);
  emit("verify", Math.round(progress.value * max));
  if (hideTimer) window.clearTimeout(hideTimer);
  hideTimer = window.setTimeout(() => {
    if (!dragging.value) showImage.value = false;
  }, 1200);
}

function reset(): void {
  progress.value = 0;
  dragging.value = false;
  showImage.value = false;
}

onBeforeUnmount(() => {
  if (hideTimer) window.clearTimeout(hideTimer);
});

defineExpose({ reset });
</script>

<style scoped lang="scss">
.fa-puzzle {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
  user-select: none;
}

.fa-puzzle__reveal {
  order: 2;
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.25s ease;
}

.fa-puzzle__reveal.is-open {
  grid-template-rows: 1fr;
}

.fa-puzzle__reveal-inner {
  min-height: 0;
  overflow: hidden;
}

.fa-puzzle__reveal.is-open .fa-puzzle__reveal-inner {
  padding-bottom: 10px;
}

.fa-puzzle__area {
  position: relative;
  width: 100%;
  aspect-ratio: 2 / 1;
  overflow: hidden;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--default-box-color);
}

.fa-puzzle__bg {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: fill;
  pointer-events: none;
}

.fa-puzzle__piece {
  position: absolute;
  height: auto;
  filter: drop-shadow(0 2px 6px rgb(0 0 0 / 45%));
  pointer-events: none;
}

.fa-puzzle__refresh {
  position: absolute;
  top: 8px;
  right: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  color: #fff;
  cursor: pointer;
  background: rgb(0 0 0 / 38%);
  border: 0;
  border-radius: 6px;
  transition: background 0.2s;

  &:hover {
    background: rgb(0 0 0 / 60%);
  }
}

.fa-puzzle__mask {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  color: var(--el-color-primary);
  background: rgb(0 0 0 / 35%);
}

.fa-puzzle__track {
  order: 1;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 40px;
  overflow: hidden;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  background: #f1f1f4;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  touch-action: none;

  &.is-dragging {
    cursor: grabbing;
  }
}

:global(html.dark) .fa-puzzle__track {
  background: #26272f;
}

.fa-puzzle__fill {
  position: absolute;
  inset: 0 auto 0 0;
  background: linear-gradient(90deg, var(--el-color-success), var(--el-color-success-light-3));
  transition: width 0.3s ease;
}

.fa-puzzle__handler {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 100%;
  color: var(--el-text-color-secondary);
  cursor: grab;
  background: var(--default-box-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  box-shadow: none;
}

.fa-puzzle__text {
  position: relative;
  z-index: 1;
  color: transparent;
  pointer-events: none;
  background: linear-gradient(
    to right,
    var(--el-text-color-secondary) 0%,
    var(--el-text-color-secondary) 40%,
    #fff 50%,
    var(--el-text-color-secondary) 60%,
    var(--el-text-color-secondary) 100%
  );
  background-size: 200% 100%;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: puzzle-shimmer 2.2s cubic-bezier(0, 0.2, 1, 1) infinite;
}

.is-passed {
  .fa-puzzle__track {
    color: var(--el-color-success);
    border-color: var(--el-color-success-light-5);
  }

  .fa-puzzle__fill {
    background: linear-gradient(90deg, var(--el-color-success), var(--el-color-success-light-3));
  }

  .fa-puzzle__handler {
    color: var(--el-color-success);
    border-color: var(--el-color-success-light-5);
  }

  .fa-puzzle__text {
    color: var(--el-color-success);
    background: none;
    -webkit-text-fill-color: currentcolor;
    animation: none;
  }
}

@keyframes puzzle-shimmer {
  0% {
    background-position: 150% 0;
  }

  100% {
    background-position: -50% 0;
  }
}

.is-loading {
  opacity: 0.75;
}
</style>
