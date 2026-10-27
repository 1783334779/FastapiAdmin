<template>
  <ElSelect
    v-model="model"
    class="wf-full"
    :aria-label="label"
    placeholder="搜索姓名或账号，选择具体人员（可多选）"
    multiple
    filterable
    remote
    remote-show-suffix
    clearable
    collapse-tags
    collapse-tags-tooltip
    :remote-method="searchUsers"
    :loading="searching"
    :no-data-text="failed ? '人员加载失败，请重新搜索' : '未找到有效人员'"
    @visible-change="(opened: boolean) => opened && searchUsers('')"
  >
    <ElOption
      v-for="person in options"
      v-show="matches(person)"
      :key="person.id"
      :value="person.id"
      :label="personLabel(person)"
    >
      <div class="project-person-option">
        <span>{{ personLabel(person) }}</span>
        <span class="project-person-option__dept">{{ departmentName(person) }}</span>
      </div>
    </ElOption>
  </ElSelect>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElOption, ElSelect } from "element-plus";
import { projectApi } from "@/api/module_business/project";
import type { Department, Person } from "@/api/module_workflow/workflow";

const model = defineModel<number[]>({ required: true });
const props = defineProps<{
  label: string;
  initialPeople: Person[];
  selectedPeople?: Person[];
  departments: Department[];
}>();
const query = ref("");
const results = ref<Person[] | null>(null);
const cached = ref(new Map<number, Person>());
const searching = ref(false);
const failed = ref(false);
let requestNumber = 0;

watch(
  () => [props.selectedPeople, props.initialPeople],
  () => {
    for (const person of [...(props.selectedPeople ?? []), ...props.initialPeople]) {
      cached.value.set(person.id, { ...cached.value.get(person.id), ...person });
    }
  },
  { immediate: true }
);

const options = computed(() => {
  const people = new Map(
    (results.value ?? props.initialPeople).map((person) => [person.id, person])
  );
  // 已选项仍保留在选项缓存中，搜索/切换结果时标签不能退化成纯数字 ID。
  for (const id of model.value) {
    const person = cached.value.get(id);
    if (person) people.set(id, person);
  }
  return [...people.values()];
});
function personLabel(person: Person) {
  return `${person.name}（${person.username || `ID ${person.id}`}）`;
}
function departmentName(person: Person) {
  return props.departments.find((dept) => dept.id === person.dept_id)?.name ?? "未配置部门";
}
function matches(person: Person) {
  const text = query.value.toLocaleLowerCase();
  return (
    !text ||
    person.name.toLocaleLowerCase().includes(text) ||
    (person.username ?? "").toLocaleLowerCase().includes(text)
  );
}
async function searchUsers(value: string) {
  const current = ++requestNumber;
  query.value = value.trim();
  failed.value = false;
  if (!query.value) {
    results.value = null;
    searching.value = false;
    return;
  }
  searching.value = true;
  try {
    const response = await projectApi.options(query.value);
    if (current !== requestNumber) return;
    results.value = response.users;
    for (const person of response.users) cached.value.set(person.id, person);
  } catch {
    if (current !== requestNumber) return;
    results.value = [];
    failed.value = true;
  } finally {
    if (current === requestNumber) searching.value = false;
  }
}
</script>

<style scoped>
.project-person-option {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
}

.project-person-option__dept {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
