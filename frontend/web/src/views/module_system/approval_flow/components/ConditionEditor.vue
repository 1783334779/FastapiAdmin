<template>
  <div class="wf-condition">
    <template v-if="model.logic">
      <div class="wf-inline">
        <ElSelect v-model="model.logic" aria-label="条件组合方式" style="width: 150px"
          ><ElOption value="AND" label="全部满足（AND）" /><ElOption
            value="OR"
            label="任一满足（OR）" /></ElSelect
        ><ElButton size="small" @click="addLeaf">加条件</ElButton
        ><ElButton v-if="depth < 4" size="small" @click="addGroup">加分组</ElButton>
      </div>
      <div v-for="(item, index) in model.items ?? []" :key="index" class="wf-stack">
        <ConditionEditor
          :model-value="item"
          :depth="depth + 1"
          @update:model-value="(value) => replaceChild(index, value)"
        /><ElButton size="small" type="danger" text @click="model.items?.splice(index, 1)"
          >删除这项</ElButton
        >
      </div>
    </template>
    <template v-else>
      <ElSelect :model-value="model.field" aria-label="条件字段" @update:model-value="changeField"
        ><ElOption v-for="item in fields" :key="item.value" :value="item.value" :label="item.label"
      /></ElSelect>
      <ElSelect v-model="model.op" aria-label="比较方式" @change="changeOperator"
        ><ElOption
          v-for="op in availableOperators"
          :key="op.value"
          :value="op.value"
          :label="op.label"
      /></ElSelect>
      <ElSelect
        v-if="isSet && model.field === 'external_purchase'"
        v-model="setValues"
        multiple
        aria-label="是否采购条件集合"
      >
        <ElOption value="true" label="是" /><ElOption value="false" label="否" />
      </ElSelect>
      <ElSelect
        v-else-if="isSet"
        v-model="setValues"
        multiple
        filterable
        allow-create
        default-first-option
        aria-label="多个条件值"
        placeholder="输入值并按回车添加"
      />
      <ElSelect
        v-else-if="model.field === 'external_purchase'"
        v-model="booleanValue"
        aria-label="是否采购条件值"
        ><ElOption :value="true" label="是" /><ElOption :value="false" label="否"
      /></ElSelect>
      <ElInputNumber
        v-else-if="isNumeric"
        v-model="numberValue"
        :min="1"
        :precision="0"
        aria-label="部门或人员ID"
      />
      <ElDatePicker
        v-else-if="isDate"
        v-model="stringValue"
        type="date"
        value-format="YYYY-MM-DD"
        aria-label="条件日期"
      />
      <ElInput
        v-else
        v-model="stringValue"
        maxlength="255"
        aria-label="条件值"
        placeholder="填写字典 value 或文字，不是标签"
      />
      <ElButton v-if="depth < 4" size="small" @click="convertGroup">改为 AND/OR 分组</ElButton>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed } from "vue";
import type { Condition } from "@/api/module_workflow/workflow";
defineOptions({ name: "ConditionEditor" });
withDefaults(defineProps<{ depth?: number }>(), { depth: 0 });
const model = defineModel<Condition>({
  default: () => ({ field: "external_purchase", op: "eq", value: true }),
});
const fields = [
  { value: "external_purchase", label: "是否对外采购" },
  { value: "initiation_type", label: "立项类型（字典值）" },
  { value: "category", label: "项目类别（字典值）" },
  { value: "currency", label: "币种（字典值）" },
  { value: "business_dept_id", label: "业务部门ID" },
  { value: "planned_start_date", label: "计划开始日期" },
  { value: "planned_end_date", label: "计划结束日期" },
  { value: "name", label: "项目名称" },
  { value: "it_manager_ids", label: "IT经理包含人员ID" },
  { value: "business_manager_ids", label: "业务经理包含人员ID" },
];
const isUsers = computed(() =>
  ["it_manager_ids", "business_manager_ids"].includes(model.value.field ?? "")
);
const isNumeric = computed(() => model.value.field === "business_dept_id" || isUsers.value);
const isDate = computed(() =>
  ["planned_start_date", "planned_end_date"].includes(model.value.field ?? "")
);
const isSet = computed(() => ["in", "not_in"].includes(model.value.op ?? ""));
const operators = [
  { value: "eq", label: "等于" },
  { value: "ne", label: "不等于" },
  { value: "in", label: "属于集合" },
  { value: "not_in", label: "不属于集合" },
  { value: "gt", label: "大于" },
  { value: "gte", label: "大于或等于" },
  { value: "lt", label: "小于" },
  { value: "lte", label: "小于或等于" },
  { value: "contains", label: "包含人员" },
];
const availableOperators = computed(() =>
  operators.filter((item) =>
    isUsers.value
      ? item.value === "contains"
      : item.value !== "contains" &&
        (isNumeric.value || isDate.value || !["gt", "gte", "lt", "lte"].includes(item.value))
  )
);
const stringValue = computed({
  get: () => String(model.value.value ?? ""),
  set: (value) => {
    model.value.value = value;
  },
});
const numberValue = computed({
  get: () => Number(model.value.value) || 1,
  set: (value) => {
    model.value.value = value ?? 1;
  },
});
const booleanValue = computed({
  get: () => model.value.value === true,
  set: (value) => {
    model.value.value = value;
  },
});
const setValues = computed({
  get: () => (Array.isArray(model.value.value) ? model.value.value.map(String) : []),
  set: (values) => {
    model.value.value = values.map((value) =>
      model.value.field === "external_purchase"
        ? value === "true"
        : isNumeric.value
          ? Number(value)
          : value
    );
  },
});
function changeField(field: string) {
  model.value = {
    field,
    op: ["it_manager_ids", "business_manager_ids"].includes(field) ? "contains" : "eq",
    value:
      field === "external_purchase"
        ? true
        : field === "business_dept_id" || field.endsWith("manager_ids")
          ? 1
          : "",
  };
}
function changeOperator() {
  if (isSet.value) model.value.value = [];
  else if (Array.isArray(model.value.value))
    model.value.value = model.value.field === "external_purchase" ? true : isNumeric.value ? 1 : "";
}
function leaf(): Condition {
  return { field: "external_purchase", op: "eq", value: true };
}
function addLeaf() {
  (model.value.items ??= []).push(leaf());
}
function addGroup() {
  (model.value.items ??= []).push({ logic: "AND", items: [leaf()] });
}
function replaceChild(index: number, value: Condition) {
  if (model.value.items) model.value.items[index] = value;
}
function convertGroup() {
  model.value = { logic: "AND", items: [JSON.parse(JSON.stringify(model.value))] };
}
</script>
