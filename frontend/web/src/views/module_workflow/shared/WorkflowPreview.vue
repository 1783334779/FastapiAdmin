<template>
  <div class="workflow-preview" aria-label="当前实例绑定的流程版本图">
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      :nodes-draggable="false"
      :nodes-connectable="false"
      :elements-selectable="false"
      fit-view-on-init
      ><Background /><Controls :show-interactive="false"
    /></VueFlow>
  </div>
</template>
<script setup lang="ts">
import { computed } from "vue";
import { VueFlow } from "@vue-flow/core";
import { Background } from "@vue-flow/background";
import { Controls } from "@vue-flow/controls";
import type { WorkflowGraph, Visit } from "@/api/module_workflow/workflow";
import "@vue-flow/core/dist/style.css";
import "@vue-flow/core/dist/theme-default.css";
import "@vue-flow/controls/dist/style.css";
const props = defineProps<{ graph: WorkflowGraph; visits?: Visit[] }>();
const nodes = computed(() =>
  props.graph.nodes.map((node) => ({
    ...node,
    type: "default",
    data: { label: node.data.label },
    style: {
      borderColor: props.visits?.some(
        (visit) => visit.node_key === node.id && visit.status === "ACTIVE"
      )
        ? "var(--el-color-primary)"
        : "var(--el-border-color)",
      background: "var(--el-bg-color)",
      color: "var(--el-text-color-primary)",
    },
  }))
);
const edges = computed(() =>
  props.graph.edges.map((edge) => ({
    ...edge,
    label: edge.is_default ? "其他情况" : edge.condition ? `条件 ${edge.priority ?? ""}` : "",
    style: { stroke: "var(--el-border-color-darker)" },
  }))
);
</script>
<style scoped>
.workflow-preview {
  height: 320px;
  border: 1px solid var(--el-border-color-light);
  border-radius: var(--fa-radius-md, 12px);
}
</style>
