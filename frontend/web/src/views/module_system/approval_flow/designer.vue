<template>
  <div v-loading="loading" class="fa-full-height wf-page">
    <section class="wf-section">
      <div class="wf-toolbar">
        <ElButton @click="router.push('/system/approval-flows')">返回配置</ElButton
        ><ElInput
          v-model="name"
          aria-label="流程名称"
          maxlength="200"
          style="width: 240px"
          :disabled="!editable"
        /><ElSelect
          v-model="selectedVersion"
          clearable
          placeholder="当前草稿"
          aria-label="查看流程版本"
          style="width: 180px"
          @change="loadVersion"
          ><ElOption
            v-for="version in versions"
            :key="version.id"
            :value="version.id"
            :label="`发布版 v${version.version_no}`" /></ElSelect
        ><span class="wf-spacer" /><ElButton
          v-if="readOnly"
          v-hasPerm="['module_system:workflow:configure']"
          @click="copyVersion"
          >复制此版为草稿</ElButton
        ><template v-else
          ><ElButton @click="validate">校验配置</ElButton
          ><ElButton
            v-hasPerm="['module_system:workflow:configure']"
            :loading="saving"
            @click="save"
            >保存草稿</ElButton
          ><ElButton
            v-hasPerm="['module_system:workflow:publish']"
            type="primary"
            :loading="saving"
            @click="publish"
            >发布新版本</ElButton
          ></template
        >
      </div>
      <ElAlert
        :closable="false"
        :type="readOnly ? 'info' : 'warning'"
        :title="
          readOnly
            ? '正在查看不可修改的发布版本；已有项目始终引用自己首次绑定的版本。'
            : '从左侧添加节点，拖动调整位置，拖拽节点连接点连线；点击节点或连线配置。草稿可未完成，发布必须校验通过。'
        "
      />
    </section>
    <div class="wf-designer">
      <aside class="wf-designer__panel">
        <div class="wf-node-palette">
          <ElButton
            v-for="item in nodeKinds"
            :key="item.type"
            :disabled="!editable"
            @click="addNode(item.type)"
            >{{ item.label }}</ElButton
          ><ElDivider /><ElButton @click="fitView()">适应画布</ElButton
          ><span class="wf-muted"
            >并行分叉必须指定配对汇合；条件出口必须配置优先级和一条默认路线。驳回不通过画回环实现。</span
          >
        </div>
      </aside>
      <div class="wf-designer__canvas">
        <VueFlow
          v-model:nodes="nodes"
          v-model:edges="edges"
          :node-types="nodeTypes"
          :nodes-draggable="editable"
          :nodes-connectable="editable"
          :edges-updatable="false"
          :delete-key-code="editable ? 'Delete' : null"
          fit-view-on-init
          @connect="connect"
          @node-click="selectNode"
          @edge-click="selectEdge"
          @pane-click="clearSelection"
          ><Background /><Controls
        /></VueFlow>
      </div>
      <aside class="wf-designer__panel wf-designer__config">
        <ElForm v-if="selectedNode" label-position="top" :disabled="!editable"
          ><ElFormItem label="节点名称"
            ><ElInput v-model="selectedNode.data.label" maxlength="100"
          /></ElFormItem>
          <div class="wf-muted">节点ID：{{ selectedNode.id }}</div>
          <template v-if="selectedNode.type === 'APPROVAL'"
            ><ElFormItem label="审批模式"
              ><ElSelect v-model="selectedNode.data.approval_mode"
                ><ElOption value="ANY" label="任意一人通过" /><ElOption
                  value="ALL"
                  label="所有人通过（会签）" /></ElSelect></ElFormItem
            ><ElAlert
              :closable="false"
              type="info"
              title="节点完成前一票否决；完成后关闭其余任务。"
            /><ElFormItem label="系统角色（可多选）"
              ><ElSelect v-model="systemRoles" multiple filterable
                ><ElOption
                  v-for="role in options.roles"
                  :key="role.id"
                  :value="role.id"
                  :label="role.name" /></ElSelect></ElFormItem
            ><ElFormItem label="业务角色（可多选）"
              ><ElSelect v-model="businessRoles" multiple filterable
                ><ElOption
                  v-for="role in options.business_roles?.filter((item) => item.enabled)"
                  :key="role.id"
                  :value="role.code"
                  :label="role.name" /></ElSelect
            ></ElFormItem>
            <p class="wf-muted">
              多个来源合并去重。提交检查所有节点，进入节点时重新找人，本次名单固定。
            </p></template
          >
          <ElFormItem v-if="selectedNode.type === 'PARALLEL'" label="配对并行汇合"
            ><ElSelect v-model="selectedNode.data.join_key"
              ><ElOption
                v-for="node in nodes.filter((item) => item.type === 'JOIN')"
                :key="node.id"
                :value="node.id"
                :label="node.data.label" /></ElSelect
          ></ElFormItem>
          <ElButton v-if="editable" type="danger" plain @click="removeNode"
            >删除节点及关联连线</ElButton
          >
        </ElForm>
        <ElForm v-else-if="selectedEdge" label-position="top" :disabled="!editable"
          ><p class="wf-muted">
            {{ nodeName(selectedEdge.source) }} → {{ nodeName(selectedEdge.target) }}
          </p>
          <template v-if="edgeIsConditional"
            ><ElFormItem label="默认路线"
              ><ElSwitch
                :model-value="selectedEdge.is_default ?? false"
                @update:model-value="setDefault" /></ElFormItem
            ><template v-if="!selectedEdge.is_default"
              ><ElFormItem label="优先级（小数值先判断）"
                ><ElInputNumber
                  v-model="selectedEdge.priority"
                  :min="0"
                  :precision="0" /></ElFormItem
              ><ElFormItem label="分支条件"
                ><ConditionEditor v-model="selectedEdge.condition" /></ElFormItem
            ></template>
            <p class="wf-muted">按优先级只走首条命中的路线；全部不匹配时走默认路线。</p></template
          ><ElAlert v-else :closable="false" type="info" title="普通连线无需条件配置。" /><ElButton
            v-if="editable"
            type="danger"
            plain
            @click="removeEdge"
            >删除连线</ElButton
          ></ElForm
        >
        <ElEmpty v-else description="点击节点或连线配置" />
      </aside>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, markRaw, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  VueFlow,
  useVueFlow,
  type Connection,
  type NodeMouseEvent,
  type EdgeMouseEvent,
} from "@vue-flow/core";
import { Background } from "@vue-flow/background";
import { Controls } from "@vue-flow/controls";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  workflowApi,
  type GraphNode,
  type GraphEdge,
  type Options,
  type FlowDefinition,
  type WorkflowGraph,
} from "@/api/module_workflow/workflow";
import CanvasNode from "./components/CanvasNode.vue";
import ConditionEditor from "./components/ConditionEditor.vue";
import { useAuth } from "@/hooks/core/useAuth";
import "@vue-flow/core/dist/style.css";
import "@vue-flow/core/dist/theme-default.css";
import "@vue-flow/controls/dist/style.css";
import "@/views/module_workflow/shared/workflow.scss";
const route = useRoute(),
  router = useRouter();
const { fitView } = useVueFlow();
const { hasAuth } = useAuth();
const nodeKinds = [
  { type: "START", label: "开始" },
  { type: "APPROVAL", label: "审核环节" },
  { type: "EXCLUSIVE", label: "条件分支" },
  { type: "MERGE", label: "条件合并" },
  { type: "PARALLEL", label: "并行分叉" },
  { type: "JOIN", label: "并行汇合" },
  { type: "END", label: "结束" },
];
const nodeTypes = Object.fromEntries(nodeKinds.map((kind) => [kind.type, markRaw(CanvasNode)]));
const nodes = ref<GraphNode[]>([]),
  edges = ref<GraphEdge[]>([]),
  name = ref(""),
  code = ref(""),
  lockVersion = ref(1),
  enabled = ref(true),
  readOnly = ref(false),
  selectedVersion = ref<number>(),
  versions = ref<NonNullable<FlowDefinition["versions"]>>([]);
const loading = ref(false),
  saving = ref(false),
  selectedNodeId = ref(""),
  selectedEdgeId = ref("");
const options = ref<Options>({
  users: [],
  departments: [],
  dictionaries: {},
  roles: [],
  business_roles: [],
});
const selectedNode = computed(() => nodes.value.find((node) => node.id === selectedNodeId.value));
const editable = computed(() => !readOnly.value && hasAuth("module_system:workflow:configure"));
const selectedEdge = computed(() => edges.value.find((edge) => edge.id === selectedEdgeId.value));
const edgeIsConditional = computed(
  () => nodes.value.find((node) => node.id === selectedEdge.value?.source)?.type === "EXCLUSIVE"
);
const systemRoles = computed({
  get: () =>
    (selectedNode.value?.data.assignees ?? [])
      .filter((rule) => rule.type === "SYSTEM_ROLE")
      .map((rule) => Number(rule.role_id)),
  set: (ids: number[]) => {
    if (selectedNode.value)
      selectedNode.value.data.assignees = [
        ...(selectedNode.value.data.assignees ?? []).filter(
          (rule) => rule.type === "BUSINESS_ROLE"
        ),
        ...ids.map((role_id) => ({ type: "SYSTEM_ROLE" as const, role_id })),
      ];
  },
});
const businessRoles = computed({
  get: () =>
    (selectedNode.value?.data.assignees ?? [])
      .filter((rule) => rule.type === "BUSINESS_ROLE")
      .map((rule) => String(rule.code)),
  set: (codes: string[]) => {
    if (selectedNode.value)
      selectedNode.value.data.assignees = [
        ...(selectedNode.value.data.assignees ?? []).filter((rule) => rule.type === "SYSTEM_ROLE"),
        ...codes.map((value) => ({ type: "BUSINESS_ROLE" as const, code: value })),
      ];
  },
});
function graph(): WorkflowGraph {
  return {
    nodes: nodes.value.map((node) => ({
      id: node.id,
      type: node.type,
      position: { x: node.position.x, y: node.position.y },
      data: JSON.parse(JSON.stringify(node.data)),
    })),
    edges: edges.value.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      ...(edge.priority !== undefined ? { priority: edge.priority } : {}),
      ...(edge.is_default ? { is_default: true } : {}),
      ...(edge.condition && !edge.is_default
        ? { condition: JSON.parse(JSON.stringify(edge.condition)) }
        : {}),
    })),
  };
}
function body() {
  return {
    code: code.value,
    name: name.value,
    enabled: enabled.value,
    graph: graph(),
    expected_version: lockVersion.value,
  };
}
function applyDefinition(value: FlowDefinition) {
  name.value = value.name;
  code.value = value.code;
  enabled.value = value.enabled;
  lockVersion.value = value.lock_version;
  versions.value = value.versions ?? [];
  readOnly.value = value.read_only ?? false;
  nodes.value = JSON.parse(JSON.stringify(value.graph?.nodes ?? []));
  edges.value = JSON.parse(JSON.stringify(value.graph?.edges ?? []));
  clearSelection();
}
async function loadVersion() {
  loading.value = true;
  try {
    applyDefinition(
      await workflowApi.detail(Number(route.params.id), selectedVersion.value || undefined)
    );
  } finally {
    loading.value = false;
  }
}
async function save() {
  saving.value = true;
  try {
    const value = await workflowApi.save(body(), Number(route.params.id));
    lockVersion.value = value.lock_version;
    ElMessage.success("草稿已保存");
    return value;
  } finally {
    saving.value = false;
  }
}
async function validate() {
  const result = await workflowApi.validate(body());
  if (result.valid) ElMessage.success("流程结构与规则配置校验通过；具体人员仍在项目提交时检查");
  else await ElMessageBox.alert(result.issues.join("\n"), "流程配置不完整");
  return result.valid;
}
async function publish() {
  if (!(await validate())) return;
  await ElMessageBox.confirm(
    "发布后本版本不可修改，已有项目继续使用其原版本。确认发布？",
    "发布新版本"
  );
  if (editable.value) await save();
  saving.value = true;
  try {
    const result = await workflowApi.publish(Number(route.params.id), lockVersion.value);
    applyDefinition(result);
    ElMessage.success("新版本已发布，可回配置页绑定项目模块");
  } finally {
    saving.value = false;
  }
}
async function copyVersion() {
  const source = graph();
  selectedVersion.value = undefined;
  await loadVersion();
  nodes.value = source.nodes;
  edges.value = source.edges;
  readOnly.value = false;
  ElMessage.info("已复制到编辑区，保存后更新草稿，不会修改旧发布版");
}
function addNode(type: string) {
  const label = nodeKinds.find((item) => item.type === type)?.label ?? type;
  nodes.value.push({
    id: `n_${crypto.randomUUID().replaceAll("-", "")}`,
    type,
    position: {
      x: 120 + (nodes.value.length % 3) * 240,
      y: 80 + Math.floor(nodes.value.length / 3) * 140,
    },
    data: {
      label,
      ...(type === "APPROVAL" ? { approval_mode: "ANY" as const, assignees: [] } : {}),
    },
  });
}
function connect(connection: Connection) {
  if (!editable.value || !connection.source || !connection.target) return;
  const conditional =
    nodes.value.find((node) => node.id === connection.source)?.type === "EXCLUSIVE";
  edges.value.push({
    id: `e_${crypto.randomUUID().replaceAll("-", "")}`,
    source: connection.source,
    target: connection.target,
    ...(conditional
      ? {
          priority: edges.value.filter((edge) => edge.source === connection.source).length,
          condition: { field: "external_purchase", op: "eq", value: true },
        }
      : {}),
  });
}
function clearSelection() {
  selectedNodeId.value = "";
  selectedEdgeId.value = "";
}
function selectNode(event: NodeMouseEvent) {
  selectedNodeId.value = event.node.id;
  selectedEdgeId.value = "";
}
function selectEdge(event: EdgeMouseEvent) {
  selectedEdgeId.value = event.edge.id;
  selectedNodeId.value = "";
}
function removeNode() {
  const id = selectedNodeId.value;
  nodes.value = nodes.value.filter((node) => node.id !== id);
  edges.value = edges.value.filter((edge) => edge.source !== id && edge.target !== id);
  clearSelection();
}
function removeEdge() {
  edges.value = edges.value.filter((edge) => edge.id !== selectedEdgeId.value);
  clearSelection();
}
function setDefault(value: string | number | boolean) {
  if (!selectedEdge.value) return;
  if (value === true)
    edges.value
      .filter((edge) => edge.source === selectedEdge.value?.source)
      .forEach((edge) => {
        edge.is_default = edge.id === selectedEdge.value?.id;
      });
  else {
    selectedEdge.value.is_default = false;
    selectedEdge.value.priority ??= 0;
    selectedEdge.value.condition ??= { field: "external_purchase", op: "eq", value: true };
  }
}
function nodeName(key: string) {
  return nodes.value.find((node) => node.id === key)?.data.label ?? key;
}
onMounted(async () => {
  options.value = await workflowApi.options();
  if (route.query.version) selectedVersion.value = Number(route.query.version);
  await loadVersion();
});
</script>
