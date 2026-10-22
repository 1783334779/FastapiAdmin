<!-- SQL 控制台：外部 MySQL/PostgreSQL（只读校验 / 确认写 / 敏感列脱敏） -->
<template>
  <div class="fa-full-height">
    <ElCard class="fa-table-card">
      <FaTableHeader v-model:columns="columnChecks" :loading="loading" @refresh="loadConnections">
        <template #left>
          <div class="flex items-center gap-2.5">
            <span class="text-base font-semibold">数据库连接</span>
            <ElButton
              v-hasPerm="['module_dbconsole:conn:create']"
              type="primary"
              :loading="createLoading"
              @click="handleAdd"
            >
              新增连接
            </ElButton>
          </div>
        </template>
      </FaTableHeader>

      <FaTable :loading="loading" :data="connections" :columns="columns" row-key="id" />
    </ElCard>

    <ElCard shadow="hover" class="fa-card mt-3">
      <template #header>
        <div class="flex items-center gap-2">
          <FaSvgIcon icon="ri:terminal-box-line" class="text-lg" />
          <span class="font-medium">执行 SQL</span>
          <span class="ml-2 text-xs text-[#909399]">
            只读语句自动校验；写语句需先开启「允许写操作」，结果最多 200 行、敏感列自动打码
          </span>
        </div>
      </template>

      <ElForm label-suffix=":" label-position="top">
        <ElRow :gutter="12">
          <ElCol :span="6">
            <ElFormItem label="连接">
              <ElSelect
                v-model="currentId"
                placeholder="选择连接"
                class="w-full"
                @change="onConnectionChange"
              >
                <ElOption
                  v-for="item in connections"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </ElSelect>
            </ElFormItem>
          </ElCol>
          <ElCol :span="6">
            <ElFormItem label="库 / schema">
              <ElSelect
                v-model="currentDatabase"
                placeholder="可空"
                class="w-full"
                clearable
                @change="loadTables"
              >
                <ElOption
                  v-for="item in databases"
                  :key="item.name"
                  :label="item.name"
                  :value="item.name"
                />
              </ElSelect>
            </ElFormItem>
          </ElCol>
          <ElCol :span="6">
            <ElFormItem label="表（选中自动填入查询）">
              <ElSelect
                v-model="currentTable"
                placeholder="可空"
                class="w-full"
                clearable
                filterable
                @change="fillTableQuery"
              >
                <ElOption
                  v-for="item in tables"
                  :key="item.name"
                  :label="item.name"
                  :value="item.name"
                />
              </ElSelect>
            </ElFormItem>
          </ElCol>
          <ElCol :span="6" class="flex items-end justify-end gap-2 pb-4">
            <span class="text-xs text-[#909399]">允许写操作</span>
            <ElSwitch v-model="confirmed" size="small" />
            <ElButton
              v-hasPerm="['module_dbconsole:query:execute']"
              type="primary"
              :loading="running"
              :disabled="!currentId"
              @click="runQuery"
            >
              执行
            </ElButton>
          </ElCol>
        </ElRow>
        <ElFormItem label="SQL">
          <ElInput
            v-model="sql"
            type="textarea"
            :rows="6"
            placeholder="select * from ...（只读语句自动校验；写语句需先开启「允许写操作」）"
          />
        </ElFormItem>
      </ElForm>

      <template v-if="result">
        <ElAlert
          v-if="result.masked_columns.length"
          type="warning"
          :closable="false"
          class="mb-2"
          :title="`敏感列已打码：${result.masked_columns.join('、')}`"
        />
        <ElAlert
          v-if="result.truncated"
          type="info"
          :closable="false"
          class="mb-2"
          title="结果超过 200 行，已截断"
        />
        <div class="mb-2 text-xs text-[#909399]">
          {{ result.read_only ? "只读查询" : "写操作" }} · {{ result.rowcount }} 行 ·
          {{ result.elapsed_ms }} ms
        </div>
        <FaTable :data="resultRows" :columns="resultColumns" max-height="360" border />
      </template>
    </ElCard>

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
import DbConsoleAPI, {
  type DbConnection,
  type DbConnectionForm,
  type DbObject,
  type DbQueryResult,
} from "@/api/module_dbconsole/connection";
import type { FormItem } from "@/components/forms/fa-form/index.vue";
import FaForm from "@/components/forms/fa-form/index.vue";
import StatusTag from "@/components/display/fa-status-tag/index.vue";
import FaTableHeader from "@/components/tables/fa-table-header/index.vue";
import type { ColumnOption } from "@/types/component";
import { renderTableOperationCell, type TableOperationAction } from "@utils";
import { ElMessage } from "element-plus";

defineOptions({
  name: "DbConsole",
  inheritAttrs: false,
});

type DbConnectionFormModel = DbConnectionForm & { id?: number };

// ── 连接列表 ──────────────────────────────────────────────────────────
const loading = ref(false);
const connections = ref<DbConnection[]>([]);

const columnChecks = ref<ColumnOption[]>([
  { prop: "name", label: "名称", minWidth: 140, showOverflowTooltip: true },
  { prop: "db_type", label: "类型", width: 110 },
  {
    prop: "host",
    label: "地址",
    minWidth: 180,
    showOverflowTooltip: true,
    formatter: (row: DbConnection) => `${row.host}:${row.port}`,
  },
  { prop: "database", label: "默认库", width: 140, showOverflowTooltip: true },
  {
    prop: "status",
    label: "状态",
    width: 90,
    align: "center",
    formatter: (row: DbConnection) =>
      h(StatusTag, {
        type: row.status === 0 ? "success" : "info",
        label: row.status === 0 ? "启用" : "停用",
      }),
  },
  { prop: "operation", label: "操作", width: 200, fixed: "right", align: "center" },
]);

const columns = computed(() =>
  columnChecks.value.map((item) =>
    item.prop === "operation"
      ? { ...item, formatter: (row: DbConnection) => formatOperationCell(row) }
      : item
  )
);

const currentId = ref<number>();
const databases = ref<DbObject[]>([]);
const tables = ref<DbObject[]>([]);
const currentDatabase = ref<string>();
const currentTable = ref<string>();
const sql = ref("select 1");
const confirmed = ref(false);
const running = ref(false);
const result = ref<DbQueryResult>();

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
  loading.value = true;
  try {
    const res = await DbConsoleAPI.listConnections();
    connections.value = res.data.data || [];
  } finally {
    loading.value = false;
  }
}

async function onConnectionChange(id: number) {
  currentDatabase.value = undefined;
  currentTable.value = undefined;
  result.value = undefined;
  const res = await DbConsoleAPI.listDatabases(id);
  databases.value = res.data.data || [];
}

async function loadTables() {
  if (!currentId.value) return;
  const res = await DbConsoleAPI.listTables(currentId.value, currentDatabase.value);
  tables.value = res.data.data || [];
}

async function fillTableQuery(table?: string) {
  if (!table) return;
  sql.value = `select * from ${table} limit 100`;
}

async function runQuery() {
  if (!currentId.value) return;
  running.value = true;
  try {
    const res = await DbConsoleAPI.runQuery(currentId.value, {
      sql: sql.value,
      confirmed: confirmed.value,
    });
    result.value = res.data.data;
    ElMessage.success(res.data?.msg || "执行成功");
  } finally {
    running.value = false;
  }
}

function buildRowActions(row: DbConnection): TableOperationAction[] {
  return [
    {
      key: "use",
      label: "使用",
      artType: "view",
      perm: "module_dbconsole:query:execute",
      run: () => void selectConnection(row),
    },
    {
      key: "edit",
      label: "编辑",
      artType: "edit",
      perm: "module_dbconsole:conn:update",
      run: () => void handleOpenDialog("update", row.id),
    },
    {
      key: "delete",
      label: "删除",
      artType: "delete",
      perm: "module_dbconsole:conn:delete",
      run: () => void deleteRow(row),
    },
  ];
}

function formatOperationCell(row: DbConnection) {
  return renderTableOperationCell(buildRowActions(row));
}

async function selectConnection(row: DbConnection) {
  currentId.value = row.id;
  await onConnectionChange(row.id);
}

async function deleteRow(row: DbConnection) {
  await confirmDelete(`确认删除连接「${row.name}」？`);
  await DbConsoleAPI.deleteConnections([row.id]);
  if (currentId.value === row.id) currentId.value = undefined;
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
  {
    label: "主机",
    key: "host",
    type: "input",
    span: 24,
    props: { placeholder: "如 127.0.0.1" },
  },
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

onMounted(loadConnections);
</script>
