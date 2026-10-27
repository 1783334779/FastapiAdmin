<template>
  <div class="approval-canvas-node" :class="{ 'is-selected': selected }">
    <Handle v-if="type !== 'START'" type="target" :position="Position.Top" />
    <div class="approval-canvas-node__type">{{ labels[type ?? "APPROVAL"] ?? type }}</div>
    <div>{{ data.label }}</div>
    <div v-if="type === 'APPROVAL'" class="wf-muted">
      {{ data.approval_mode === "ALL" ? "全部通过 · 一票否决" : "任一通过 · 一票否决" }}
    </div>
    <Handle v-if="type !== 'END'" type="source" :position="Position.Bottom" />
  </div>
</template>
<script setup lang="ts">
import { Handle, Position, type NodeProps } from "@vue-flow/core";
import type { GraphNode } from "@/api/module_workflow/workflow";
defineProps<NodeProps<GraphNode["data"]>>();
const labels: Record<string, string> = {
  START: "开始",
  END: "结束",
  APPROVAL: "审核",
  EXCLUSIVE: "条件分支",
  MERGE: "条件合并",
  PARALLEL: "并行分叉",
  JOIN: "并行汇合",
};
</script>
<style scoped>
.approval-canvas-node {
  min-width: 180px;
  padding: 12px 16px;
  color: var(--el-text-color-primary);
  text-align: center;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: var(--fa-radius-md, 12px);
}

.approval-canvas-node.is-selected {
  border-color: var(--el-color-primary);
}

.approval-canvas-node__type {
  margin-bottom: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
