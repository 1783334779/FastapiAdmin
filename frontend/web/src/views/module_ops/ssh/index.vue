<!-- SSH 运维：主机/命令片段/批量执行/终端（POST 轮询）与日志跟踪 -->
<template>
  <div class="fa-full-height">
    <ElTabs v-model="activeTab" class="fa-tabs-fill">
      <!-- 主机管理 -->
      <ElTabPane label="主机管理" name="host">
        <ElCard class="fa-table-card">
          <FaTableHeader
            v-model:columns="hostColumnChecks"
            :loading="hostLoading"
            @refresh="loadHosts"
          >
            <template #left>
              <div class="flex items-center gap-2.5">
                <span class="text-base font-semibold">SSH 主机</span>
                <ElButton
                  v-hasPerm="['module_ops:ssh:create']"
                  type="primary"
                  :loading="createLoading"
                  @click="handleAdd"
                >
                  新增主机
                </ElButton>
              </div>
            </template>
          </FaTableHeader>

          <FaTable :loading="hostLoading" :data="hosts" :columns="hostColumns" row-key="id" />
        </ElCard>
      </ElTabPane>

      <!-- 命令片段 -->
      <ElTabPane label="命令片段" name="snippet">
        <ElCard class="fa-table-card">
          <FaTableHeader
            v-model:columns="snippetColumnChecks"
            :loading="snippetLoading"
            @refresh="loadSnippets"
          >
            <template #left>
              <div class="flex items-center gap-2.5">
                <span class="text-base font-semibold">常用命令</span>
                <ElButton
                  v-hasPerm="['module_ops:snippet:create']"
                  type="primary"
                  @click="handleSnippetAdd"
                >
                  新增片段
                </ElButton>
              </div>
            </template>
          </FaTableHeader>

          <FaTable
            :loading="snippetLoading"
            :data="snippets"
            :columns="snippetColumns"
            row-key="id"
          />
        </ElCard>
      </ElTabPane>

      <!-- 批量执行 -->
      <ElTabPane label="批量执行" name="batch">
        <ElCard shadow="hover" class="fa-card">
          <template #header>
            <div class="flex items-center gap-2">
              <FaSvgIcon icon="ri:play-list-line" class="text-lg" />
              <span class="font-medium">多主机批量执行</span>
              <span class="ml-2 text-xs text-[#909399]">
                命令原样交给远端 shell；执行会写入操作审计日志
              </span>
            </div>
          </template>

          <ElForm label-suffix=":" label-position="top">
            <ElRow :gutter="12">
              <ElCol :span="18">
                <ElFormItem label="目标主机（最多 50）">
                  <ElSelect
                    v-model="batchHostIds"
                    multiple
                    collapse-tags
                    collapse-tags-tooltip
                    filterable
                    placeholder="选择目标主机"
                    class="w-full"
                  >
                    <ElOption
                      v-for="item in hosts"
                      :key="item.id"
                      :label="item.name"
                      :value="item.id"
                    />
                  </ElSelect>
                </ElFormItem>
              </ElCol>
              <ElCol :span="6" class="flex items-end justify-end gap-2 pb-4">
                <ElButton
                  v-hasPerm="['module_ops:ssh:exec']"
                  type="primary"
                  :loading="batchRunning"
                  :disabled="!batchHostIds.length"
                  @click="runBatch"
                >
                  执行
                </ElButton>
              </ElCol>
            </ElRow>
            <ElFormItem label="命令">
              <ElInput
                v-model="batchCommand"
                type="textarea"
                :rows="4"
                placeholder="例如：uptime && df -h（可先在「命令片段」里维护常用命令）"
              />
            </ElFormItem>
          </ElForm>

          <template v-if="batchResults.length">
            <FaTable :data="batchResults" :columns="batchColumns" max-height="360" border>
              <template #ok="{ row }">
                <ElTag :type="row.ok ? 'success' : 'danger'" size="small">
                  {{ row.ok ? "成功" : "失败" }}
                </ElTag>
              </template>
              <template #output="{ row }">
                <pre class="m-0 max-h-40 overflow-auto text-xs whitespace-pre-wrap">{{
                  row.stdout || row.stderr || row.error
                }}</pre>
              </template>
            </FaTable>
          </template>
        </ElCard>
      </ElTabPane>

      <!-- 终端（POST 轮询） -->
      <ElTabPane label="终端" name="terminal">
        <ElCard shadow="hover" class="fa-card">
          <template #header>
            <div class="flex items-center gap-2">
              <FaSvgIcon icon="ri:terminal-window-line" class="text-lg" />
              <span class="font-medium">终端会话</span>
              <span class="ml-2 text-xs text-[#909399]">
                轮询式会话（约 700ms 拉取）；空闲 30 分钟自动回收
              </span>
            </div>
          </template>

          <ElForm label-suffix=":" label-position="top">
            <ElRow :gutter="12">
              <ElCol :span="6">
                <ElFormItem label="主机">
                  <ElSelect v-model="terminalHostId" placeholder="选择主机" class="w-full">
                    <ElOption
                      v-for="item in hosts"
                      :key="item.id"
                      :label="item.name"
                      :value="item.id"
                    />
                  </ElSelect>
                </ElFormItem>
              </ElCol>
              <ElCol :span="10">
                <ElFormItem label="日志跟踪路径（可选）">
                  <ElInput v-model="logPath" placeholder="如 /var/log/nginx/error.log" clearable />
                </ElFormItem>
              </ElCol>
              <ElCol :span="8" class="flex items-end justify-end gap-2 pb-4">
                <ElButton
                  v-hasPerm="['module_ops:ssh:terminal']"
                  type="primary"
                  :loading="terminalOpening"
                  :disabled="!terminalHostId"
                  @click="openTerminal"
                >
                  打开终端
                </ElButton>
                <ElButton
                  v-hasPerm="['module_ops:ssh:terminal']"
                  :loading="terminalOpening"
                  :disabled="!terminalHostId || !logPath"
                  @click="openLogTail"
                >
                  日志跟踪
                </ElButton>
                <ElButton :disabled="!terminalSessionId" @click="closeTerminal">关闭</ElButton>
              </ElCol>
            </ElRow>
          </ElForm>

          <div class="mb-2 text-xs text-[#909399]">
            <template v-if="terminalSession">
              会话 {{ terminalSession.session_id.slice(0, 8) }} · {{ terminalSession.host_name }}
            </template>
            <template v-else>尚未打开终端会话</template>
          </div>
          <pre
            ref="terminalRef"
            class="terminal-output m-0 h-[46vh] overflow-auto rounded bg-[#1e1e1e] p-3 text-xs text-[#d4d4d4] whitespace-pre-wrap"
            >{{ terminalOutput || "（打开终端后在此显示输出）" }}</pre
          >
          <div class="mt-2 flex items-center gap-2">
            <ElInput
              v-model="terminalInput"
              placeholder="输入命令后回车（发送到当前终端会话）"
              :disabled="!terminalSessionId"
              @keyup.enter="sendTerminalInput"
            />
            <ElButton :disabled="!terminalSessionId" @click="sendTerminalInput">发送</ElButton>
          </div>
        </ElCard>
      </ElTabPane>
    </ElTabs>

    <!-- 主机新增/修改 -->
    <FaDialog
      v-model="dialogVisible.visible"
      :title="dialogVisible.title"
      width="680px"
      dialog-class="crud-embed-dialog"
      modal-class="crud-embed-dialog"
      :form-mode="dialogVisible.type"
      :confirm-loading="submitLoading"
      @cancel="handleCloseDialog"
      @confirm="handleSubmit"
    >
      <FaForm
        :key="formRenderKey"
        ref="dataFormRef"
        v-model="formData"
        :items="formItems"
        :rules="rules"
        label-suffix=":"
        :label-width="100"
        label-position="right"
        :span="24"
        :gutter="16"
        :show-reset="false"
        :show-submit="false"
        class="crud-dialog-art-form"
      />
    </FaDialog>

    <!-- 片段新增 -->
    <FaDialog
      v-model="snippetDialogVisible.visible"
      :title="snippetDialogVisible.title"
      width="560px"
      dialog-class="crud-embed-dialog"
      modal-class="crud-embed-dialog"
      :form-mode="snippetDialogVisible.type"
      :confirm-loading="snippetSubmitLoading"
      @cancel="handleSnippetClose"
      @confirm="handleSnippetSubmit"
    >
      <FaForm
        :key="snippetFormRenderKey"
        ref="snippetFormRef"
        v-model="snippetFormData"
        :items="snippetFormItems"
        :rules="snippetRules"
        label-suffix=":"
        :label-width="90"
        label-position="right"
        :span="24"
        :gutter="16"
        :show-reset="false"
        :show-submit="false"
        class="crud-dialog-art-form"
      />
    </FaDialog>
  </div>
</template>

<script lang="ts" setup>
import SshAPI, {
  type BatchExecResult,
  type SshHost,
  type SshHostForm,
  type SshSnippet,
  type TerminalSession,
} from "@/api/module_ops/ssh";
import type { FormItem } from "@/components/forms/fa-form/index.vue";
import FaForm from "@/components/forms/fa-form/index.vue";
import StatusTag from "@/components/display/fa-status-tag/index.vue";
import FaTableHeader from "@/components/tables/fa-table-header/index.vue";
import type { ColumnOption } from "@/types/component";
import { renderTableOperationCell, type TableOperationAction } from "@utils";
import { ElMessage } from "element-plus";

defineOptions({
  name: "SshOps",
  inheritAttrs: false,
});

const activeTab = ref("host");
const hosts = ref<SshHost[]>([]);
const snippets = ref<SshSnippet[]>([]);
const hostLoading = ref(false);
const snippetLoading = ref(false);

// ── 主机列表 ──────────────────────────────────────────────────────────
const hostColumnChecks = ref<ColumnOption[]>([
  { prop: "name", label: "名称", minWidth: 140, showOverflowTooltip: true },
  {
    prop: "host",
    label: "地址",
    minWidth: 180,
    showOverflowTooltip: true,
    formatter: (row: SshHost) => `${row.host}:${row.port}`,
  },
  { prop: "username", label: "用户", width: 120 },
  {
    prop: "auth_type",
    label: "认证",
    width: 100,
    formatter: (row: SshHost) => (row.auth_type === "key" ? "私钥" : "密码"),
  },
  {
    prop: "status",
    label: "状态",
    width: 90,
    align: "center",
    formatter: (row: SshHost) =>
      h(StatusTag, {
        type: row.status === 0 ? "success" : "info",
        label: row.status === 0 ? "启用" : "停用",
      }),
  },
  { prop: "operation", label: "操作", width: 200, fixed: "right", align: "center" },
]);

const hostColumns = computed(() =>
  hostColumnChecks.value.map((item) =>
    item.prop === "operation"
      ? { ...item, formatter: (row: SshHost) => formatHostOperationCell(row) }
      : item
  )
);

async function loadHosts() {
  hostLoading.value = true;
  try {
    const res = await SshAPI.listHosts();
    hosts.value = res.data.data || [];
  } finally {
    hostLoading.value = false;
  }
}

function buildHostRowActions(row: SshHost): TableOperationAction[] {
  return [
    {
      key: "test",
      label: "测试",
      artType: "view",
      perm: "module_ops:ssh:query",
      run: () => void testHost(row),
    },
    {
      key: "edit",
      label: "编辑",
      artType: "edit",
      perm: "module_ops:ssh:update",
      run: () => void handleOpenDialog("update", row.id),
    },
    {
      key: "delete",
      label: "删除",
      artType: "delete",
      perm: "module_ops:ssh:delete",
      run: () => void deleteHost(row),
    },
  ];
}

function formatHostOperationCell(row: SshHost) {
  return renderTableOperationCell(buildHostRowActions(row));
}

async function testHost(row: SshHost) {
  const res = await SshAPI.testHost(row.id);
  ElMessage.success(res.data?.msg || "连接成功");
}

async function deleteHost(row: SshHost) {
  await confirmDelete(`确认删除主机「${row.name}」？`);
  await SshAPI.deleteHosts([row.id]);
  await loadHosts();
}

// ── 主机表单 ──────────────────────────────────────────────────────────
type SshHostFormModel = SshHostForm & { id?: number };

const { dialogVisible } = useCrudDialog();
const dataFormRef = ref<InstanceType<typeof FaForm> | null>(null);
const formRenderKey = ref(0);

const initialFormData: SshHostFormModel = {
  id: undefined,
  name: "",
  host: "",
  port: 22,
  username: "root",
  auth_type: "password",
  password: "",
  private_key: "",
  passphrase: "",
  status: 0,
  description: "",
};
const formData = ref<SshHostFormModel>({ ...initialFormData });

const formItems = computed<FormItem[]>(() => {
  const isKey = formData.value.auth_type === "key";
  return [
    { label: "名称", key: "name", type: "input", span: 24, props: { placeholder: "唯一名称" } },
    { label: "地址", key: "host", type: "input", span: 24, props: { placeholder: "如 10.0.0.1" } },
    {
      label: "端口",
      key: "port",
      type: "number",
      span: 24,
      props: { controlsPosition: "right", min: 1, max: 65535, style: { width: "160px" } },
    },
    { label: "用户名", key: "username", type: "input", span: 24 },
    {
      label: "认证方式",
      key: "auth_type",
      type: "radiogroup",
      span: 24,
      props: {
        options: [
          { label: "密码", value: "password" },
          { label: "私钥", value: "key" },
        ],
      },
    },
    {
      label: "密码",
      key: "password",
      type: "input",
      span: 24,
      hidden: isKey,
      props: { type: "password", showPassword: true, placeholder: "修改时不填表示不变" },
    },
    {
      label: "私钥",
      key: "private_key",
      type: "input",
      span: 24,
      hidden: !isKey,
      props: { type: "textarea", rows: 6, placeholder: "-----BEGIN OPENSSH PRIVATE KEY-----" },
    },
    {
      label: "私钥口令",
      key: "passphrase",
      type: "input",
      span: 24,
      hidden: !isKey,
      props: { type: "password", showPassword: true, placeholder: "可选" },
    },
    {
      label: "状态",
      key: "status",
      type: "radiogroup",
      span: 24,
      props: {
        options: [
          { label: "启用", value: 0 },
          { label: "停用", value: 1 },
        ],
      },
    },
    { label: "备注", key: "description", type: "input", span: 24 },
  ];
});

const rules = computed(() => {
  const isCreate = dialogVisible.type === "create";
  const isKey = formData.value.auth_type === "key";
  return {
    name: [{ required: true, message: "请输入名称", trigger: "blur" }],
    host: [{ required: true, message: "请输入地址", trigger: "blur" }],
    username: [{ required: true, message: "请输入用户名", trigger: "blur" }],
    password:
      isCreate && !isKey ? [{ required: true, message: "请输入密码", trigger: "blur" }] : [],
    private_key:
      isCreate && isKey ? [{ required: true, message: "请输入私钥", trigger: "blur" }] : [],
  };
});

const createLoading = ref(false);

async function handleAdd() {
  createLoading.value = true;
  try {
    await handleOpenDialog("create");
  } finally {
    createLoading.value = false;
  }
}

const { submitLoading, handleCloseDialog, handleOpenDialog, handleSubmit } =
  useCrudForm<SshHostFormModel>({
    formData,
    initialFormData,
    dialogVisible,
    dataFormRef,
    formRenderKey,
    detailApi: SshAPI.detailHost,
    createApi: SshAPI.createHost,
    updateApi: SshAPI.updateHost,
    titles: { create: "新增主机", update: "修改主机" },
    onUpdateSuccess: loadHosts,
    onCreateSuccess: loadHosts,
  });

// ── 片段列表 ──────────────────────────────────────────────────────────
const snippetColumnChecks = ref<ColumnOption[]>([
  { prop: "name", label: "名称", minWidth: 140, showOverflowTooltip: true },
  { prop: "command", label: "命令", minWidth: 320, showOverflowTooltip: true },
  { prop: "description", label: "备注", minWidth: 160, showOverflowTooltip: true },
  { prop: "operation", label: "操作", width: 200, fixed: "right", align: "center" },
]);

const snippetColumns = computed(() =>
  snippetColumnChecks.value.map((item) =>
    item.prop === "operation"
      ? { ...item, formatter: (row: SshSnippet) => formatSnippetOperationCell(row) }
      : item
  )
);

async function loadSnippets() {
  snippetLoading.value = true;
  try {
    const res = await SshAPI.listSnippets();
    snippets.value = res.data.data || [];
  } finally {
    snippetLoading.value = false;
  }
}

function buildSnippetRowActions(row: SshSnippet): TableOperationAction[] {
  return [
    {
      key: "apply",
      label: "填入批量执行",
      artType: "view",
      perm: "module_ops:ssh:exec",
      run: () => {
        batchCommand.value = row.command;
        activeTab.value = "batch";
      },
    },
    {
      key: "delete",
      label: "删除",
      artType: "delete",
      perm: "module_ops:snippet:delete",
      run: () => void deleteSnippet(row),
    },
  ];
}

function formatSnippetOperationCell(row: SshSnippet) {
  return renderTableOperationCell(buildSnippetRowActions(row));
}

async function deleteSnippet(row: SshSnippet) {
  await confirmDelete(`确认删除片段「${row.name}」？`);
  await SshAPI.deleteSnippets([row.id]);
  await loadSnippets();
}

// ── 片段表单 ──────────────────────────────────────────────────────────
type SshSnippetFormModel = {
  id?: number;
  name: string;
  command: string;
  description?: string | null;
};

const { dialogVisible: snippetDialogVisible } = useCrudDialog();
const snippetFormRef = ref<InstanceType<typeof FaForm> | null>(null);
const snippetFormRenderKey = ref(0);

const initialSnippetForm: SshSnippetFormModel = {
  id: undefined,
  name: "",
  command: "",
  description: "",
};
const snippetFormData = ref<SshSnippetFormModel>({ ...initialSnippetForm });

const snippetFormItems = computed<FormItem[]>(() => [
  { label: "名称", key: "name", type: "input", span: 24 },
  {
    label: "命令",
    key: "command",
    type: "input",
    span: 24,
    props: { type: "textarea", rows: 4, placeholder: "如 df -h" },
  },
  { label: "备注", key: "description", type: "input", span: 24 },
]);

const snippetRules = computed(() => ({
  name: [{ required: true, message: "请输入名称", trigger: "blur" }],
  command: [{ required: true, message: "请输入命令", trigger: "blur" }],
}));

const snippetFormSnippet = () => snippets.value;

const {
  submitLoading: snippetSubmitLoading,
  handleCloseDialog: handleSnippetClose,
  handleOpenDialog: handleSnippetOpen,
  handleSubmit: handleSnippetSubmit,
} = useCrudForm<SshSnippetFormModel>({
  formData: snippetFormData,
  initialFormData: initialSnippetForm,
  dialogVisible: snippetDialogVisible,
  dataFormRef: snippetFormRef,
  formRenderKey: snippetFormRenderKey,
  detailApi: (snippetId: number) => {
    const row = snippetFormSnippet().find((item) => item.id === snippetId);
    return Promise.resolve({ data: { data: row } });
  },
  createApi: SshAPI.createSnippet,
  updateApi: SshAPI.updateSnippet,
  titles: { create: "新增命令片段", update: "修改命令片段" },
  onUpdateSuccess: loadSnippets,
  onCreateSuccess: loadSnippets,
});

function handleSnippetAdd() {
  void handleSnippetOpen("create");
}

// ── 批量执行 ──────────────────────────────────────────────────────────
const batchHostIds = ref<number[]>([]);
const batchCommand = ref("");
const batchRunning = ref(false);
const batchResults = ref<BatchExecResult[]>([]);

const batchColumns = ref<ColumnOption[]>([
  { prop: "host_name", label: "主机", width: 140 },
  { prop: "ok", label: "结果", width: 90, align: "center" },
  { prop: "exit_status", label: "退出码", width: 90 },
  { prop: "output", label: "输出", minWidth: 360 },
  { prop: "elapsed_ms", label: "耗时(ms)", width: 100 },
]);

async function runBatch() {
  if (!batchHostIds.value.length || !batchCommand.value.trim()) {
    ElMessage.warning("请选择主机并填写命令");
    return;
  }
  batchRunning.value = true;
  try {
    const res = await SshAPI.batchExec({
      host_ids: batchHostIds.value,
      command: batchCommand.value,
      timeout: 15,
    });
    batchResults.value = res.data.data || [];
    ElMessage.success("批量执行完成");
  } finally {
    batchRunning.value = false;
  }
}

// ── 终端（POST 轮询）──────────────────────────────────────────────────
const terminalHostId = ref<number>();
const terminalOpening = ref(false);
const terminalSession = ref<TerminalSession>();
const terminalSessionId = computed(() => terminalSession.value?.session_id || "");
const terminalOutput = ref("");
const terminalInput = ref("");
const terminalRef = ref<HTMLElement>();
const logPath = ref("");
let pollTimer: number | undefined;

function b64encode(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  bytes.forEach((byte) => (binary += String.fromCharCode(byte)));
  return btoa(binary);
}

function b64decode(value: string): string {
  const binary = atob(value);
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function appendOutput(text: string) {
  terminalOutput.value = (terminalOutput.value + text).slice(-200_000);
  nextTick(() => {
    if (terminalRef.value) terminalRef.value.scrollTop = terminalRef.value.scrollHeight;
  });
}

function startPolling() {
  stopPolling();
  pollTimer = window.setInterval(async () => {
    if (!terminalSessionId.value) return;
    try {
      const res = await SshAPI.pollTerminal(terminalSessionId.value, 1.2);
      const payload = res.data.data;
      if (payload?.data) appendOutput(b64decode(payload.data));
      if (payload?.closed) {
        appendOutput("\n[会话已结束]\n");
        stopPolling();
      }
    } catch {
      stopPolling();
    }
  }, 700);
}

function stopPolling() {
  if (pollTimer !== undefined) {
    window.clearInterval(pollTimer);
    pollTimer = undefined;
  }
}

async function openTerminal() {
  if (!terminalHostId.value) return;
  terminalOpening.value = true;
  try {
    const res = await SshAPI.openTerminal({ host_id: terminalHostId.value, cols: 120, rows: 30 });
    terminalSession.value = res.data.data;
    terminalOutput.value = "";
    appendOutput(`[已连接 ${terminalSession.value?.host_name}]\n`);
    startPolling();
  } finally {
    terminalOpening.value = false;
  }
}

async function openLogTail() {
  if (!terminalHostId.value || !logPath.value.trim()) return;
  terminalOpening.value = true;
  try {
    const res = await SshAPI.openLog({
      host_id: terminalHostId.value,
      path: logPath.value.trim(),
      lines: 200,
    });
    terminalSession.value = res.data.data;
    terminalOutput.value = "";
    appendOutput(`[日志跟踪 ${logPath.value}]\n`);
    startPolling();
  } finally {
    terminalOpening.value = false;
  }
}

async function sendTerminalInput() {
  if (!terminalSessionId.value) return;
  const text = terminalInput.value;
  terminalInput.value = "";
  await SshAPI.inputTerminal(terminalSessionId.value, b64encode(`${text}\r`));
}

async function closeTerminal() {
  const sessionId = terminalSessionId.value;
  stopPolling();
  terminalSession.value = undefined;
  if (sessionId) {
    await SshAPI.closeTerminal(sessionId).catch(() => undefined);
  }
  appendOutput("\n[已关闭]\n");
}

onMounted(async () => {
  await loadHosts();
  await loadSnippets();
});

onBeforeUnmount(() => stopPolling());
</script>

<style scoped>
.terminal-output {
  font-family: "SFMono-Regular", Menlo, Consolas, monospace;
}
</style>
