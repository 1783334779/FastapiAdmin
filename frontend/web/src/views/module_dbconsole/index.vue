<!-- SQL 控制台：左侧连接/库表导航 + 右侧编辑器与结果区（外部 MySQL/PostgreSQL） -->
<template>
  <div class="fa-full-height">
    <ElSplitter style="height: 100%">
      <!-- 左：连接 + 库表 -->
      <ElSplitterPanel :size="300" :min="240" :max="420">
        <div class="flex h-full min-h-0 flex-col">
          <div class="flex items-center justify-between px-3 py-2">
            <span class="text-sm font-semibold">数据库连接</span>
            <ElButton
              v-hasPerm="['module_dbconsole:conn:create']"
              link
              type="primary"
              :loading="createLoading"
              @click="handleAdd"
            >
              <ElIcon class="mr-1"><Plus /></ElIcon>新增
            </ElButton>
          </div>

          <ElScrollbar class="min-h-0 flex-1 px-2">
            <div
              v-for="item in connections"
              :key="item.id"
              class="conn-item"
              :class="{ 'is-active': item.id === currentId }"
              @click="selectConnection(item)"
            >
              <span
                class="status-dot"
                :style="{
                  background:
                    item.status === 0 ? 'var(--el-color-success)' : 'var(--el-color-info)',
                }"
              />
              <div class="min-w-0 flex-1">
                <div class="truncate text-[13px]">{{ item.name }}</div>
                <div class="truncate text-xs text-[#909399]">
                  {{ item.db_type }} · {{ item.host }}:{{ item.port }}
                </div>
              </div>
              <ElDropdown
                trigger="click"
                @command="(cmd) => handleConnCommand(String(cmd), item)"
                @click.stop
              >
                <ElIcon class="more-icon"><MoreFilled /></ElIcon>
                <template #dropdown>
                  <ElDropdownMenu>
                    <ElDropdownItem command="test">测试连接</ElDropdownItem>
                    <ElDropdownItem command="edit">编辑</ElDropdownItem>
                    <ElDropdownItem command="delete" divided>删除</ElDropdownItem>
                  </ElDropdownMenu>
                </template>
              </ElDropdown>
            </div>
            <ElEmpty v-if="!connections.length" description="暂无连接" :image-size="56" />
          </ElScrollbar>

          <div class="section-title">库 / 表</div>
          <ElScrollbar class="min-h-0 flex-1 px-2 pb-2">
            <div v-if="!currentId" class="p-2 text-xs text-[#909399]">先选择一个连接</div>
            <template v-else>
              <div class="tree-group">库 / schema</div>
              <div
                v-for="db in databases"
                :key="`db-${db.name}`"
                class="tree-item"
                :class="{ 'is-active': db.name === currentDatabase }"
                @click="pickDatabase(db.name)"
              >
                {{ db.name }}
              </div>
              <div class="tree-group mt-2">表</div>
              <div
                v-for="table in tables"
                :key="`t-${table.name}`"
                class="tree-item"
                @click="insertTable(table.name)"
              >
                {{ table.name }}
              </div>
              <div v-if="!tables.length" class="p-2 text-xs text-[#909399]">
                选择库后加载表（点击表名自动填入查询）
              </div>
            </template>
          </ElScrollbar>
        </div>
      </ElSplitterPanel>

      <!-- 右：编辑器 + 结果 -->
      <ElSplitterPanel :min="480">
        <div class="flex h-full min-h-0 flex-col">
          <div
            class="flex items-center gap-2 border-b border-(--el-border-color-lighter) px-3 py-2"
          >
            <span class="text-sm font-semibold">SQL 控制台</span>
            <ElTag v-if="currentConnection" size="small" type="info">
              {{ currentConnection.name }}
            </ElTag>
            <span v-else class="text-xs text-[#909399]">未选择连接</span>
            <div class="ml-auto flex items-center gap-3">
              <span class="text-xs text-[#909399]">允许写操作</span>
              <ElSwitch v-model="confirmed" size="small" />
              <ElDropdown trigger="click" :disabled="!history.length" @command="applyHistory">
                <ElButton :disabled="!history.length">
                  <ElIcon class="mr-1"><Clock /></ElIcon>历史
                </ElButton>
                <template #dropdown>
                  <ElDropdownMenu>
                    <ElDropdownItem v-for="(item, index) in history" :key="index" :command="item">
                      {{ item.length > 60 ? `${item.slice(0, 60)}…` : item }}
                    </ElDropdownItem>
                  </ElDropdownMenu>
                </template>
              </ElDropdown>
              <ElButton
                v-hasPerm="['module_dbconsole:query:execute']"
                type="primary"
                :loading="running"
                :disabled="!currentId"
                @click="runQuery"
              >
                执行
              </ElButton>
              <ElButton :disabled="!sql" @click="clearEditor">清空</ElButton>
            </div>
          </div>

          <div class="px-3 pt-3">
            <ElInput
              v-model="sql"
              type="textarea"
              :rows="8"
              resize="vertical"
              class="sql-editor"
              placeholder="select * from ...（只读语句自动校验；写语句需先开启「允许写操作」）"
              @keydown.ctrl.enter.prevent="runQuery"
            />
            <div class="mt-1 text-right text-xs text-[#909399]">Ctrl + Enter 执行</div>
          </div>

          <div class="flex min-h-0 flex-1 flex-col px-3 pb-3">
            <ElAlert
              v-if="queryError"
              type="error"
              :closable="false"
              class="mb-2"
              :title="queryError"
            />
            <template v-if="result">
              <div class="mb-2 flex flex-wrap items-center gap-2 text-xs">
                <ElTag size="small" :type="result.read_only ? 'info' : 'warning'">
                  {{ result.read_only ? "只读查询" : "写操作" }}
                </ElTag>
                <span class="text-[#909399]"
                  >{{ result.rowcount }} 行 · {{ result.elapsed_ms }} ms</span
                >
                <ElTag v-if="result.masked_columns.length" size="small" type="warning">
                  已脱敏：{{ result.masked_columns.join("、") }}
                </ElTag>
                <ElTag v-if="result.truncated" size="small" type="info">已截断 200 行</ElTag>
              </div>
              <FaTable
                :data="resultRows"
                :columns="resultColumns"
                height="100%"
                border
                class="min-h-0 flex-1"
              />
            </template>
            <ElEmpty
              v-else-if="!queryError"
              class="mt-10"
              description="执行 SQL 后在此显示结果"
              :image-size="72"
            />
          </div>

          <div
            class="flex items-center gap-2 border-t border-(--el-border-color-lighter) px-3 py-1.5 text-xs text-[#909399]"
          >
            <span>
              {{
                currentConnection
                  ? `${currentConnection.name} · ${currentConnection.db_type}`
                  : "未选择连接"
              }}
            </span>
            <span v-if="currentDatabase">· {{ currentDatabase }}</span>
            <span v-if="lastRun" class="ml-auto">
              上次执行 {{ lastRun.rows }} 行 · {{ lastRun.ms }} ms
            </span>
          </div>
        </div>
      </ElSplitterPanel>
    </ElSplitter>

    <FaDialog
      v-model="dialogVisible.visible"
      :title="dialogVisible.title"
      width="640px"
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
  </div>
</template>

<script lang="ts" setup>
import { Clock, MoreFilled, Plus } from "@element-plus/icons-vue";
import DbConsoleAPI, {
  type DbConnection,
  type DbConnectionForm,
  type DbObject,
  type DbQueryResult,
} from "@/api/module_dbconsole/connection";
import type { FormItem } from "@/components/forms/fa-form/index.vue";
import FaForm from "@/components/forms/fa-form/index.vue";
import type { ColumnOption } from "@/types/component";
import { ElMessage } from "element-plus";

defineOptions({
  name: "DbConsole",
  inheritAttrs: false,
});

type DbConnectionFormModel = DbConnectionForm & { id?: number };

// ── 连接与库表 ────────────────────────────────────────────────────────
const connections = ref<DbConnection[]>([]);
const currentId = ref<number>();
const currentConnection = computed(() =>
  connections.value.find((item) => item.id === currentId.value)
);
const databases = ref<DbObject[]>([]);
const tables = ref<DbObject[]>([]);
const currentDatabase = ref<string>();

const sql = ref("select 1");
const confirmed = ref(false);
const running = ref(false);
const result = ref<DbQueryResult>();
const queryError = ref("");
const lastRun = ref<{ rows: number; ms: number }>();
const history = ref<string[]>([]);
const HISTORY_KEY = "dbconsole:history";

function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    history.value = raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    history.value = [];
  }
}

function pushHistory(text: string) {
  if (!text) return;
  history.value = [text, ...history.value.filter((item) => item !== text)].slice(0, 10);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.value));
}

function applyHistory(text: string) {
  sql.value = text;
}

function extractErrorMessage(error: unknown): string {
  const err = error as { response?: { data?: { msg?: string } }; message?: string };
  return err?.response?.data?.msg || err?.message || "执行失败";
}

const resultColumns = computed<ColumnOption[]>(() =>
  (result.value?.columns ?? []).map((name, index) => ({
    prop: `c${index}`,
    label: name,
    minWidth: 140,
    showOverflowTooltip: true,
  }))
);

const resultRows = computed<Record<string, unknown>[]>(() =>
  (result.value?.rows ?? []).map((row) =>
    Object.fromEntries(row.map((value, index) => [`c${index}`, value]))
  )
);

async function loadConnections() {
  const res = await DbConsoleAPI.listConnections();
  connections.value = res.data.data || [];
  if (currentId.value && !connections.value.some((item) => item.id === currentId.value)) {
    currentId.value = undefined;
    databases.value = [];
    tables.value = [];
  }
}

async function selectConnection(row: DbConnection) {
  currentId.value = row.id;
  currentDatabase.value = undefined;
  tables.value = [];
  result.value = undefined;
  const res = await DbConsoleAPI.listDatabases(row.id);
  databases.value = res.data.data || [];
}

async function pickDatabase(name: string) {
  currentDatabase.value = name;
  if (!currentId.value) return;
  const res = await DbConsoleAPI.listTables(currentId.value, name);
  tables.value = res.data.data || [];
}

function insertTable(name: string) {
  sql.value = `select * from ${name} limit 100`;
}

function clearEditor() {
  sql.value = "";
}

async function runQuery() {
  if (!currentId.value) {
    ElMessage.warning("请先选择一个连接");
    return;
  }
  if (!sql.value.trim()) {
    ElMessage.warning("请先输入 SQL");
    return;
  }
  running.value = true;
  queryError.value = "";
  try {
    const res = await DbConsoleAPI.runQuery(currentId.value, {
      sql: sql.value,
      confirmed: confirmed.value,
    });
    result.value = res.data.data;
    if (result.value) {
      lastRun.value = { rows: result.value.rowcount, ms: result.value.elapsed_ms };
    }
    pushHistory(sql.value.trim());
  } catch (error) {
    result.value = undefined;
    queryError.value = extractErrorMessage(error);
  } finally {
    running.value = false;
  }
}

function handleConnCommand(command: string, row: DbConnection) {
  if (command === "test") {
    void DbConsoleAPI.testConnection(row.id).then((res) =>
      ElMessage.success(res.data?.msg || "连接成功")
    );
  } else if (command === "edit") {
    void handleOpenDialog("update", row.id);
  } else if (command === "delete") {
    void deleteRow(row);
  }
}

async function deleteRow(row: DbConnection) {
  await confirmDelete(`确认删除连接「${row.name}」？`);
  await DbConsoleAPI.deleteConnections([row.id]);
  if (currentId.value === row.id) {
    currentId.value = undefined;
    databases.value = [];
    tables.value = [];
    result.value = undefined;
  }
  await loadConnections();
}

// ── 新增 / 修改 ───────────────────────────────────────────────────────
const { dialogVisible } = useCrudDialog();
const dataFormRef = ref<InstanceType<typeof FaForm> | null>(null);
const formRenderKey = ref(0);

const initialFormData: DbConnectionFormModel = {
  id: undefined,
  name: "",
  db_type: "mysql",
  host: "",
  port: 3306,
  username: "",
  password: "",
  database: "",
  description: "",
  status: 0,
};
const formData = ref<DbConnectionFormModel>({ ...initialFormData });

const formItems = computed<FormItem[]>(() => [
  {
    label: "名称",
    key: "name",
    type: "input",
    span: 24,
    props: { placeholder: "唯一名称", maxlength: 64 },
  },
  {
    label: "类型",
    key: "db_type",
    type: "select",
    span: 24,
    props: {
      options: [
        { label: "MySQL", value: "mysql" },
        { label: "PostgreSQL", value: "postgres" },
      ],
    },
  },
  { label: "主机", key: "host", type: "input", span: 24, props: { placeholder: "如 127.0.0.1" } },
  {
    label: "端口",
    key: "port",
    type: "number",
    span: 24,
    props: { controlsPosition: "right", min: 1, max: 65535, style: { width: "160px" } },
  },
  { label: "用户名", key: "username", type: "input", span: 24 },
  {
    label: "密码",
    key: "password",
    type: "input",
    span: 24,
    props: { type: "password", showPassword: true, placeholder: "修改时不填表示不变" },
  },
  { label: "默认库", key: "database", type: "input", span: 24, props: { placeholder: "可空" } },
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
]);

const rules = computed(() => ({
  name: [{ required: true, message: "请输入名称", trigger: "blur" }],
  db_type: [{ required: true, message: "请选择类型", trigger: "change" }],
  host: [{ required: true, message: "请输入主机", trigger: "blur" }],
  port: [{ required: true, message: "请输入端口", trigger: "blur" }],
  username: [{ required: true, message: "请输入用户名", trigger: "blur" }],
  password:
    dialogVisible.type === "create"
      ? [{ required: true, message: "请输入密码", trigger: "blur" }]
      : [],
}));

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
  useCrudForm<DbConnectionFormModel>({
    formData,
    initialFormData,
    dialogVisible,
    dataFormRef,
    formRenderKey,
    detailApi: DbConsoleAPI.detailConnection,
    createApi: DbConsoleAPI.createConnection,
    updateApi: DbConsoleAPI.updateConnection,
    titles: { create: "新增连接", update: "修改连接" },
    onUpdateSuccess: loadConnections,
    onCreateSuccess: loadConnections,
  });

onMounted(() => {
  loadHistory();
  void loadConnections();
});
</script>

<style lang="scss" scoped>
:deep(.el-splitter) {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  box-shadow: var(--el-box-shadow-light);
}

:deep(.el-splitter-panel) {
  overflow: hidden;
}

.conn-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  margin-bottom: 2px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.15s;

  &:hover {
    background: var(--el-fill-color-light);
  }

  &.is-active {
    background: var(--el-color-primary-light-9);
  }

  .more-icon {
    opacity: 0;
    color: var(--el-text-color-secondary);
    transition: opacity 0.15s;
    flex-shrink: 0;
  }

  &:hover .more-icon {
    opacity: 1;
  }
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.section-title {
  padding: 8px 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  border-top: 1px solid var(--el-border-color-lighter);
}

.tree-group {
  padding: 6px 8px 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.tree-item {
  padding: 5px 10px;
  margin-bottom: 1px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;

  &:hover {
    background: var(--el-fill-color-light);
  }

  &.is-active {
    color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
  }
}

.sql-editor :deep(.el-textarea__inner) {
  font-family: "SFMono-Regular", Menlo, Consolas, monospace;
  font-size: 13px;
  line-height: 1.6;
}
</style>
