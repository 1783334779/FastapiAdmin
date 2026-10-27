<template>
  <div v-loading="loading" class="fa-full-height wf-page">
    <section class="wf-section">
      <ElTabs v-model="tab">
        <ElTabPane label="流程与模块绑定" name="flows">
          <div class="wf-toolbar">
            <ElButton
              v-hasPerm="['module_system:workflow:configure']"
              type="primary"
              @click="newVisible = true"
              ><FaSvgIcon icon="ri:add-line" />新建流程</ElButton
            ><span class="wf-muted">配置后先发布，再绑定项目模块。已有项目不跟随新版本变化。</span
            ><span class="wf-spacer" /><ElButton @click="load">刷新</ElButton>
          </div>
          <ElTable :data="flows" row-key="id"
            ><ElTableColumn
              prop="name"
              label="流程名称"
              min-width="200"
              show-overflow-tooltip /><ElTableColumn
              prop="code"
              label="稳定编码"
              min-width="150"
              show-overflow-tooltip /><ElTableColumn label="状态" width="120"
              ><template #default="{ row }"
                ><FaStatusTag
                  :type="row.enabled ? 'success' : 'info'"
                  :label="row.enabled ? '启用' : '停用'" /></template></ElTableColumn
            ><ElTableColumn label="发布情况" width="130"
              ><template #default="{ row }">{{
                row.published_version_id ? "已有发布版本" : "仅草稿"
              }}</template></ElTableColumn
            ><ElTableColumn label="操作" fixed="right" width="200"
              ><template #default="{ row }"
                ><ElButton link @click="router.push(`/system/approval-flows/${row.id}/design`)"
                  >设计/查看版本</ElButton
                ><ElButton
                  v-hasPerm="['module_system:workflow:configure']"
                  link
                  @click="toggleFlow(row as FlowDefinition)"
                  >{{ row.enabled ? "停用" : "启用" }}</ElButton
                ></template
              ></ElTableColumn
            ><template #empty
              ><ElEmpty description="暂无流程，先创建草稿并配置审核节点。" /></template
          ></ElTable>
          <ElDivider />
          <ElForm label-position="left" label-width="180px" class="binding-form"
            ><ElFormItem label="部门负责人系统角色"
              ><ElSelect v-model="binding.manager_role_id" clearable filterable class="wf-full"
                ><ElOption
                  v-for="role in options.roles"
                  :key="role.id"
                  :value="role.id"
                  :label="`${role.name}（${role.code}）`" /></ElSelect></ElFormItem
            ><ElFormItem label="项目模块默认流程"
              ><ElSelect v-model="binding.definition_id" clearable class="wf-full"
                ><ElOption
                  v-for="flow in flows.filter((item) => item.enabled && item.published_version_id)"
                  :key="flow.id"
                  :value="flow.id"
                  :label="flow.name" /></ElSelect></ElFormItem
            ><ElFormItem
              ><ElButton
                v-hasPerm="['module_system:workflow:configure']"
                :loading="saving"
                @click="saveBinding"
                >保存绑定与负责人角色</ElButton
              ></ElFormItem
            ></ElForm
          >
          <ElAlert
            :closable="false"
            type="info"
            title="首次配置顺序"
            description="先选部门负责人系统角色并保存 → 到成员管理部门配置每个人的管理范围 → 检查业务角色 → 设计、发布流程 → 选择默认流程并保存绑定。项目字典选项需在现有字典管理维护。"
          />
        </ElTabPane>
        <ElTabPane label="业务角色" name="roles">
          <div class="wf-toolbar">
            <ElButton
              v-hasPerm="['module_system:workflow:configure']"
              type="primary"
              @click="editRole()"
              >新增业务角色</ElButton
            ><span class="wf-muted"
              >业务角色是找人规则，不是系统角色成员名单；规则修改只影响以后发布的流程版本。</span
            >
          </div>
          <ElTable :data="businessRoles"
            ><ElTableColumn prop="name" label="业务角色" min-width="170" /><ElTableColumn
              prop="code"
              label="稳定编码"
              min-width="190"
              show-overflow-tooltip
            /><ElTableColumn label="找人策略" min-width="160"
              ><template #default="{ row }">{{
                row.strategy === "FIELD_USERS"
                  ? `单据人员字段：${row.config.field}`
                  : `创建部门最近负责人，角色 ${row.config.role_id ?? "使用模块绑定"}`
              }}</template></ElTableColumn
            ><ElTableColumn label="状态" width="110"
              ><template #default="{ row }"
                ><FaStatusTag
                  :type="row.enabled ? 'success' : 'info'"
                  :label="row.enabled ? '启用' : '停用'" /></template></ElTableColumn
            ><ElTableColumn label="操作" width="180" fixed="right"
              ><template #default="{ row }"
                ><ElButton
                  v-hasPerm="['module_system:workflow:configure']"
                  link
                  @click="editRole(row as BusinessRole)"
                  >编辑规则</ElButton
                ></template
              ></ElTableColumn
            ></ElTable
          >
        </ElTabPane>
        <ElTabPane label="成员管理部门" name="members">
          <div class="wf-toolbar">
            <ElSelect
              v-model="memberRoleId"
              filterable
              clearable
              placeholder="选择要配置成员的系统角色"
              aria-label="系统角色"
              style="width: 300px"
              @change="loadMembers"
              ><ElOption
                v-for="role in options.roles"
                :key="role.id"
                :value="role.id"
                :label="role.name" /></ElSelect
            ><ElButton @click="loadMembers">刷新成员</ElButton>
          </div>
          <ElAlert
            :closable="false"
            type="info"
            title="管理范围属于“角色＋人员”，不是人员自己的所属部门"
            description="先在用户管理给人员分配该角色，再在这里选择其管理部门。列表查看包含下级部门；审批按创建部门逐级向上，找到最近有人的一级就停止。"
          />
          <ElTable :data="members"
            ><ElTableColumn prop="name" label="角色成员" min-width="150" /><ElTableColumn
              label="本人所属部门"
              min-width="150"
              ><template #default="{ row }">{{
                options.departments.find((item) => item.id === row.dept_id)?.name ?? "未配置"
              }}</template></ElTableColumn
            ><ElTableColumn label="管理部门（可多选）" min-width="300"
              ><template #default="{ row }"
                ><ElTreeSelect
                  v-model="row.managed_dept_ids"
                  :data="departments"
                  :props="{ label: 'name', children: 'children' }"
                  node-key="id"
                  multiple
                  check-strictly
                  show-checkbox
                  filterable
                  collapse-tags
                  collapse-tags-tooltip
                  class="wf-full" /></template></ElTableColumn
            ><ElTableColumn label="操作" width="180" fixed="right"
              ><template #default="{ row }"
                ><ElButton
                  v-hasPerm="['module_system:workflow:configure']"
                  link
                  :loading="savingMember === row.id"
                  @click="saveMember(row as Person & { managed_dept_ids: number[] })"
                  >保存管理范围</ElButton
                ></template
              ></ElTableColumn
            ><template #empty
              ><ElEmpty
                description="请选择角色；若无成员，请先在用户管理给人员分配该角色。" /></template
          ></ElTable>
        </ElTabPane>
      </ElTabs>
    </section>
    <ElDrawer v-model="newVisible" title="新建审批流程" size="520px"
      ><ElForm label-position="top"
        ><ElFormItem label="流程名称" required
          ><ElInput v-model="newName" maxlength="200" /></ElFormItem
        ><ElFormItem label="稳定编码" required
          ><ElInput
            v-model="newCode"
            maxlength="64"
            placeholder="字母开头，仅字母、数字、下划线" /></ElFormItem></ElForm
      ><template #footer
        ><ElButton @click="newVisible = false">取消</ElButton
        ><ElButton type="primary" :loading="saving" @click="createFlow"
          >创建并设计</ElButton
        ></template
      ></ElDrawer
    >
    <ElDrawer v-model="roleVisible" title="配置业务角色" size="520px"
      ><ElForm label-position="top"
        ><ElFormItem label="业务角色名称" required
          ><ElInput v-model="roleForm.name" maxlength="100" /></ElFormItem
        ><ElFormItem label="稳定编码" required
          ><ElInput
            v-model="roleForm.code"
            :disabled="!!editingRoleId"
            maxlength="64" /></ElFormItem
        ><ElFormItem label="找人策略"
          ><ElSelect v-model="roleForm.strategy" @change="roleForm.config = {}"
            ><ElOption value="FIELD_USERS" label="取单据人员字段" /><ElOption
              value="DEPT_MANAGER"
              label="创建部门最近负责人" /></ElSelect></ElFormItem
        ><ElFormItem v-if="roleForm.strategy === 'FIELD_USERS'" label="人员字段" required
          ><ElSelect v-model="roleForm.config.field"
            ><ElOption value="it_manager_ids" label="IT 项目经理" /><ElOption
              value="business_manager_ids"
              label="业务项目经理" /><ElOption
              value="creator_user_id"
              label="创建人" /></ElSelect></ElFormItem
        ><ElFormItem v-else label="负责人系统角色" required
          ><ElSelect v-model="roleForm.config.role_id" filterable
            ><ElOption
              v-for="role in options.roles"
              :key="role.id"
              :value="role.id"
              :label="role.name" /></ElSelect></ElFormItem
        ><ElFormItem label="是否启用"><ElSwitch v-model="roleForm.enabled" /></ElFormItem></ElForm
      ><template #footer
        ><ElButton @click="roleVisible = false">取消</ElButton
        ><ElButton type="primary" :loading="saving" @click="saveRole">保存规则</ElButton></template
      ></ElDrawer
    >
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  workflowApi,
  departmentTree,
  type BusinessRole,
  type FlowDefinition,
  type Options,
  type Person,
} from "@/api/module_workflow/workflow";
import "@/views/module_workflow/shared/workflow.scss";
const router = useRouter(),
  route = useRoute();
const tab = ref(route.query.tab === "members" ? "members" : "flows");
const flows = ref<FlowDefinition[]>([]),
  options = ref<Options>({
    users: [],
    departments: [],
    dictionaries: {},
    roles: [],
    business_roles: [],
  }),
  businessRoles = ref<BusinessRole[]>([]);
const binding = ref<{ definition_id?: number; manager_role_id?: number }>({});
const loading = ref(false),
  saving = ref(false),
  memberRoleId = ref<number>(),
  savingMember = ref<number>();
const members = ref<(Person & { managed_dept_ids: number[] })[]>([]);
const departments = computed(() => departmentTree(options.value.departments));
const newVisible = ref(false),
  newName = ref(""),
  newCode = ref("");
const roleVisible = ref(false),
  editingRoleId = ref<number>();
const roleForm = ref<Omit<BusinessRole, "id">>({
  code: "",
  name: "",
  strategy: "FIELD_USERS",
  config: { field: "it_manager_ids" },
  enabled: true,
});
async function load() {
  loading.value = true;
  try {
    const [definitions, settings, directory] = await Promise.all([
      workflowApi.list(),
      workflowApi.binding(),
      workflowApi.options(),
    ]);
    flows.value = definitions;
    binding.value = settings;
    options.value = directory;
    businessRoles.value = directory.business_roles ?? [];
    if (!memberRoleId.value)
      memberRoleId.value = Number(route.query.role_id) || settings.manager_role_id;
    if (memberRoleId.value) await loadMembers();
  } finally {
    loading.value = false;
  }
}
async function saveBinding() {
  saving.value = true;
  try {
    await workflowApi.bind({
      definition_id: binding.value.definition_id ?? null,
      manager_role_id: binding.value.manager_role_id ?? null,
    });
    ElMessage.success("绑定配置已保存；不改变已有实例的流程版本");
  } finally {
    saving.value = false;
  }
}
async function createFlow() {
  saving.value = true;
  try {
    const graph = {
      nodes: [
        { id: "start", type: "START", position: { x: 280, y: 80 }, data: { label: "开始" } },
        {
          id: "approval",
          type: "APPROVAL",
          position: { x: 280, y: 240 },
          data: { label: "审核", approval_mode: "ANY", assignees: [] },
        },
        { id: "end", type: "END", position: { x: 280, y: 400 }, data: { label: "结束" } },
      ],
      edges: [
        { id: "e1", source: "start", target: "approval" },
        { id: "e2", source: "approval", target: "end" },
      ],
    };
    const result = await workflowApi.save({
      code: newCode.value,
      name: newName.value,
      graph,
      enabled: true,
    });
    newVisible.value = false;
    await router.push(`/system/approval-flows/${result.id}/design`);
  } finally {
    saving.value = false;
  }
}
async function toggleFlow(flow: FlowDefinition) {
  await ElMessageBox.confirm(
    `${flow.enabled ? "停用后新项目不能使用此模板，旧实例仍继续运行。" : "确认启用此模板？"}`,
    "模板状态"
  );
  const detail = await workflowApi.detail(flow.id);
  await workflowApi.save(
    {
      code: detail.code,
      name: detail.name,
      graph: detail.graph,
      enabled: !detail.enabled,
      expected_version: detail.lock_version,
    },
    flow.id
  );
  await load();
}
function editRole(role?: BusinessRole) {
  editingRoleId.value = role?.id;
  roleForm.value = role
    ? {
        code: role.code,
        name: role.name,
        strategy: role.strategy,
        config: JSON.parse(JSON.stringify(role.config)),
        enabled: role.enabled,
      }
    : {
        code: "",
        name: "",
        strategy: "FIELD_USERS",
        config: { field: "it_manager_ids" },
        enabled: true,
      };
  roleVisible.value = true;
}
async function saveRole() {
  saving.value = true;
  try {
    await workflowApi.saveRole(roleForm.value, editingRoleId.value);
    roleVisible.value = false;
    ElMessage.success("规则已保存，旧发布版本不受影响");
    await load();
  } finally {
    saving.value = false;
  }
}
async function loadMembers() {
  members.value = memberRoleId.value ? await workflowApi.members(memberRoleId.value) : [];
}
async function saveMember(member: Person & { managed_dept_ids: number[] }) {
  if (!memberRoleId.value) return;
  savingMember.value = member.id;
  try {
    await workflowApi.saveScope(memberRoleId.value, member.id, member.managed_dept_ids);
    ElMessage.success("成员管理范围已保存");
  } finally {
    savingMember.value = undefined;
  }
}
onMounted(load);
</script>
<style scoped>
.binding-form {
  max-width: 720px;
}
</style>
