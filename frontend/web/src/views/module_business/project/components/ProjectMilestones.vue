<template>
  <div class="project-milestones">
    <div class="wf-toolbar">
      <strong>项目里程碑</strong>
      <span class="wf-muted">{{ model.length }} / {{ MAX_MILESTONES }}</span>
      <span v-if="!readOnly" class="wf-muted">随项目一起保存，最多 20 个</span>
      <span class="wf-spacer" />
      <ElButton
        v-if="!readOnly"
        type="primary"
        :disabled="disabled || model.length >= MAX_MILESTONES"
        @click="open()"
      >
        <FaSvgIcon icon="ri:add-line" />新增里程碑
      </ElButton>
    </div>
    <ElTable :data="model" class="wf-full">
      <ElTableColumn type="index" label="序号" width="56" />
      <ElTableColumn prop="name" label="里程碑名称" min-width="160" show-overflow-tooltip />
      <ElTableColumn
        prop="delivery_standard"
        label="交付标准"
        min-width="180"
        show-overflow-tooltip
      />
      <ElTableColumn label="责任人" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">{{ ownerNames(row.owner_user_ids) }}</template>
      </ElTableColumn>
      <ElTableColumn label="计划开始时间" width="150">
        <template #default="{ row }">{{ displayTime(row.planned_start_time) }}</template>
      </ElTableColumn>
      <ElTableColumn label="计划结束时间" width="150">
        <template #default="{ row }">{{ displayTime(row.planned_end_time) }}</template>
      </ElTableColumn>
      <ElTableColumn v-if="!readOnly" label="操作" fixed="right" width="180">
        <template #default="{ $index, row }">
          <ElButton link :disabled="disabled" @click="open($index)">编辑</ElButton>
          <ElButton link type="danger" :disabled="disabled" @click="remove($index, row.name)"
            >移除</ElButton
          >
        </template>
      </ElTableColumn>
      <template #empty>
        <ElEmpty
          :description="
            readOnly ? '该版项目资料暂无里程碑' : '暂无里程碑，可新增计划和责任人后随项目保存'
          "
        />
      </template>
    </ElTable>
    <FaDrawer
      v-if="!readOnly"
      v-model="drawerOpen"
      :title="editingIndex === null ? '新增里程碑' : '编辑里程碑'"
      size="min(560px, 100vw)"
      :form-mode="editingIndex === null ? 'create' : 'update'"
      :close-on-click-modal="false"
      @confirm="confirm"
      @cancel="drawerOpen = false"
    >
      <ElForm
        ref="formRef"
        :model="draft"
        :rules="rules"
        label-width="110px"
        label-position="left"
        :disabled="disabled"
      >
        <ElFormItem label="里程碑名称" prop="name">
          <ElInput
            v-model="draft.name"
            maxlength="200"
            show-word-limit
            placeholder="例如：需求确认"
          />
        </ElFormItem>
        <ElFormItem label="交付标准" prop="delivery_standard">
          <ElInput
            v-model="draft.delivery_standard"
            type="textarea"
            :rows="4"
            maxlength="1000"
            show-word-limit
            placeholder="描述该里程碑应交付的成果和验收要求"
          />
        </ElFormItem>
        <ElFormItem label="责任人" prop="owner_user_ids">
          <ProjectPersonSelect
            v-model="draft.owner_user_ids"
            label="里程碑责任人"
            :initial-people="initialPeople"
            :selected-people="knownPeople"
            :departments="departments"
            @selected-people-change="rememberPeople"
          />
        </ElFormItem>
        <ElFormItem label="计划开始时间" prop="planned_start_time">
          <ElDatePicker
            v-model="draft.planned_start_time"
            type="datetime"
            format="YYYY-MM-DD HH:mm"
            value-format="YYYY-MM-DDTHH:mm:ss"
            class="wf-full"
            placeholder="选择计划开始时间"
            @change="validateEndTime"
          />
        </ElFormItem>
        <ElFormItem label="计划结束时间" prop="planned_end_time">
          <ElDatePicker
            v-model="draft.planned_end_time"
            type="datetime"
            format="YYYY-MM-DD HH:mm"
            value-format="YYYY-MM-DDTHH:mm:ss"
            class="wf-full"
            placeholder="选择计划结束时间"
          />
        </ElFormItem>
        <p class="wf-muted">
          确认仅更新当前表单，需点击页面顶部“保存草稿”或“提交审批”才会发送到后端。
        </p>
      </ElForm>
      <template #footer>
        <ElButton @click="drawerOpen = false">取消</ElButton>
        <ElButton type="primary" :disabled="disabled" :loading="confirming" @click="confirm"
          >确认</ElButton
        >
      </template>
    </FaDrawer>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from "vue";
import dayjs from "dayjs";
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from "element-plus";
import type { Department, Person, ProjectMilestoneInput } from "@/api/module_workflow/workflow";
import FaDrawer from "@/components/modal/fa-drawer/index.vue";
import ProjectPersonSelect from "./ProjectPersonSelect.vue";

const MAX_MILESTONES = 20;
const model = defineModel<ProjectMilestoneInput[]>({ default: () => [] });
const props = withDefaults(
  defineProps<{
    readOnly?: boolean;
    disabled?: boolean;
    initialPeople?: Person[];
    selectedPeople?: Person[];
    departments?: Department[];
  }>(),
  {
    readOnly: false,
    disabled: false,
    initialPeople: () => [],
    selectedPeople: () => [],
    departments: () => [],
  }
);

function emptyMilestone(): ProjectMilestoneInput {
  return {
    name: "",
    delivery_standard: "",
    owner_user_ids: [],
    planned_start_time: "",
    planned_end_time: "",
  };
}
const drawerOpen = ref(false);
const confirming = ref(false);
const editingIndex = ref<number | null>(null);
const draft = ref(emptyMilestone());
const formRef = ref<FormInstance>();
const peopleCache = ref(new Map<number, Person>());
const knownPeople = computed(() => {
  const people = new Map(
    [...props.initialPeople, ...props.selectedPeople].map((person) => [person.id, person])
  );
  for (const [id, person] of peopleCache.value) people.set(id, person);
  return [...people.values()];
});
function rememberPeople(people: Person[]) {
  for (const person of people) {
    const cached = peopleCache.value.get(person.id);
    if (
      !cached ||
      cached.name !== person.name ||
      cached.username !== person.username ||
      cached.dept_id !== person.dept_id
    )
      peopleCache.value.set(person.id, person);
  }
}
function ownerNames(ids: number[] = []) {
  return (
    ids
      .map((id) => knownPeople.value.find((person) => person.id === id)?.name ?? `用户 ${id}`)
      .join("、") || "—"
  );
}
function displayTime(value: string) {
  return value && dayjs(value).isValid() ? dayjs(value).format("YYYY-MM-DD HH:mm") : "—";
}
function inputTime(value: string) {
  return value && dayjs(value).isValid() ? dayjs(value).format("YYYY-MM-DDTHH:mm:ss") : value;
}
function periodError(item: ProjectMilestoneInput): string | undefined {
  if (!item.planned_start_time || !dayjs(item.planned_start_time).isValid())
    return "请选择有效的计划开始时间";
  if (!item.planned_end_time || !dayjs(item.planned_end_time).isValid())
    return "请选择有效的计划结束时间";
  if (dayjs(item.planned_end_time).isBefore(dayjs(item.planned_start_time)))
    return "计划结束时间不能早于计划开始时间";
}
function milestoneError(item: ProjectMilestoneInput): string | undefined {
  if (!item.name?.trim() || item.name.length > 200) return "请填写里程碑名称，最多200字";
  if (!item.delivery_standard?.trim() || item.delivery_standard.length > 1000)
    return "请填写交付标准，最多1000字";
  if (
    !item.owner_user_ids?.length ||
    item.owner_user_ids.some((id) => !Number.isInteger(id) || id <= 0)
  )
    return "请至少选择一名有效责任人";
  return periodError(item);
}
const rules: FormRules = {
  name: [
    {
      required: true,
      whitespace: true,
      max: 200,
      message: "请填写里程碑名称，最多200字",
      trigger: "blur",
    },
  ],
  delivery_standard: [
    {
      required: true,
      whitespace: true,
      max: 1000,
      message: "请填写交付标准，最多1000字",
      trigger: "blur",
    },
  ],
  owner_user_ids: [
    { type: "array", required: true, min: 1, message: "请至少选择一名责任人", trigger: "change" },
  ],
  planned_start_time: [{ required: true, message: "请选择计划开始时间", trigger: "change" }],
  planned_end_time: [
    {
      validator: (_rule, _value, callback) => {
        const error = periodError(draft.value);
        callback(error ? new Error(error) : undefined);
      },
      trigger: "change",
      required: true,
    },
  ],
};
async function validateEndTime() {
  if (draft.value.planned_end_time)
    await formRef.value?.validateField("planned_end_time").catch(() => {});
}
async function open(index?: number) {
  if (props.disabled || props.readOnly) return;
  if (index === undefined && model.value.length >= MAX_MILESTONES) return;
  editingIndex.value = index ?? null;
  const source = index === undefined ? emptyMilestone() : model.value[index];
  if (!source) return;
  draft.value = {
    name: source.name,
    delivery_standard: source.delivery_standard,
    owner_user_ids: [...source.owner_user_ids],
    planned_start_time: inputTime(source.planned_start_time),
    planned_end_time: inputTime(source.planned_end_time),
  };
  drawerOpen.value = true;
  await nextTick();
  formRef.value?.clearValidate();
}
async function confirm() {
  if (props.disabled || props.readOnly || confirming.value || !drawerOpen.value) return;
  confirming.value = true;
  try {
    try {
      if (!(await formRef.value?.validate())) return;
    } catch {
      return;
    }
    const error = milestoneError(draft.value);
    if (error) {
      ElMessage.warning(error);
      return;
    }
    const item = {
      ...draft.value,
      name: draft.value.name.trim(),
      delivery_standard: draft.value.delivery_standard.trim(),
      owner_user_ids: [...new Set(draft.value.owner_user_ids)],
    };
    if (editingIndex.value === null) {
      if (model.value.length >= MAX_MILESTONES) return;
      model.value = [...model.value, item];
    } else {
      model.value = model.value.map((current, index) =>
        index === editingIndex.value ? item : current
      );
    }
    drawerOpen.value = false;
  } finally {
    confirming.value = false;
  }
}
async function remove(index: number, name: string) {
  if (props.disabled || props.readOnly) return;
  const target = model.value[index];
  const confirmed = await ElMessageBox.confirm(
    `确认从当前表单移除“${name}”？保存项目后生效。`,
    "移除里程碑",
    { type: "warning" }
  ).then(
    () => true,
    () => false
  );
  if (confirmed && !props.disabled && !props.readOnly)
    model.value = model.value.filter((item) => item !== target);
}
function validate() {
  if (drawerOpen.value) {
    ElMessage.warning("请先确认或取消正在编辑的里程碑");
    return false;
  }
  if (model.value.length > MAX_MILESTONES) {
    ElMessage.warning("项目里程碑最多20个");
    return false;
  }
  for (const [index, item] of model.value.entries()) {
    const error = milestoneError(item);
    if (error) {
      ElMessage.warning(`第${index + 1}个里程碑：${error}`);
      return false;
    }
  }
  return true;
}
defineExpose({ validate });
</script>

<style scoped>
.project-milestones {
  min-width: 0;
}
</style>
