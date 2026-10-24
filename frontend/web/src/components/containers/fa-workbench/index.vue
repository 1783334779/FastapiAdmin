<!-- 工作区：FastHub 式「左卡片 + 间距 + 右卡片」，间距内可拖拽但无可见分割线 -->
<template>
  <div class="fa-workbench">
    <ElSplitter :layout="isCompact ? 'vertical' : 'horizontal'" style="flex: 1; min-height: 0">
      <ElSplitterPanel
        :size="isCompact ? `${sideHeight}px` : `${sideWidth}px`"
        :min="isCompact ? 200 : 160"
        :max="isCompact ? 420 : 640"
      >
        <slot name="side" />
      </ElSplitterPanel>
      <ElSplitterPanel :min="isCompact ? 240 : 300">
        <div class="fa-workbench__main">
          <slot />
        </div>
      </ElSplitterPanel>
    </ElSplitter>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";

defineOptions({ name: "FaWorkbench" });

withDefaults(
  defineProps<{
    /** 左栏宽度（水平） */
    sideWidth?: number;
    /** 窄屏上下布局时上栏高度 */
    sideHeight?: number;
  }>(),
  {
    sideWidth: 380,
    sideHeight: 320,
  }
);

const isCompact = ref(window.innerWidth < 1280);
const onResize = () => {
  isCompact.value = window.innerWidth < 1280;
};

onMounted(() => window.addEventListener("resize", onResize));
onBeforeUnmount(() => window.removeEventListener("resize", onResize));
</script>

<style lang="scss" scoped>
.fa-workbench {
  display: flex;
  flex: 1;
  min-height: 0;
}

.fa-workbench__main {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: auto;
}

.fa-workbench__main > * {
  flex: 1 1 auto;
  min-height: 0;
}

/* 12px 热区 + 正中 1px 分割线；EP 自带双层线隐藏 */
.fa-workbench :deep(.el-splitter-bar),
.fa-workbench :deep(.el-splitter-bar:hover),
.fa-workbench :deep(.el-splitter-bar.is-active) {
  width: 12px !important;
  min-width: 12px;
  background: transparent !important;
  box-shadow: none !important;
  cursor: col-resize;
}

.fa-workbench :deep(.el-splitter-bar__line),
.fa-workbench :deep(.el-splitter-bar__dragger::before),
.fa-workbench :deep(.el-splitter-bar__dragger::after),
.fa-workbench :deep(.el-splitter-bar::before) {
  display: none !important;
  content: none !important;
}

/* 我们自己画一条 1px，避免 EP 双层线叠粗 */
.fa-workbench :deep(.el-splitter-bar)::after {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  display: block;
  width: 1px;
  content: "";
  background: var(--fa-border, #e6e8ec);
}

@media (width <= 1280px) {
  .fa-workbench :deep(.el-splitter-bar) {
    width: auto !important;
    height: 12px;
    cursor: row-resize;
  }

  .fa-workbench :deep(.el-splitter-bar)::after {
    top: 50%;
    right: 0;
    bottom: auto;
    left: 0;
    width: auto;
    height: 1px;
  }
}
</style>
