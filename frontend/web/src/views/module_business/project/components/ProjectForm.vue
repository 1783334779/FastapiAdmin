<template>
  <div class="wf-stack">
    <ElAlert
      v-if="missingDictionaries"
      type="warning"
      :closable="false"
      title="项目字典尚未配置完整"
      description="请管理员在字典管理维护项目立项类型、项目类别、项目币种的有效选项；此处不会使用虚构业务选项。"
    />
    <ElForm
      ref="formRef"
      :model="model"
      :rules="rules"
      :disabled="disabled"
      label-width="130px"
      label-position="left"
    >
      <ElRow :gutter="16">
        <ElCol :xs="24" :md="12"
          ><ElFormItem label="项目名称" prop="name"
            ><ElInput v-model="model.name" maxlength="200" show-word-limit /></ElFormItem
        ></ElCol>
        <ElCol :xs="24" :md="12"
          ><ElFormItem label="立项类型" prop="initiation_type"
            ><ElSelect v-model="model.initiation_type" class="wf-full" filterable
              ><ElOption
                v-for="item in options.dictionaries.initiation_type"
                :key="item.value"
                :label="item.label"
                :value="item.value" /></ElSelect></ElFormItem
        ></ElCol>
        <ElCol :xs="24" :md="12"
          ><ElFormItem label="项目类别" prop="category"
            ><ElSelect v-model="model.category" class="wf-full" filterable
              ><ElOption
                v-for="item in options.dictionaries.category"
                :key="item.value"
                :label="item.label"
                :value="item.value" /></ElSelect></ElFormItem
        ></ElCol>
        <ElCol :xs="24" :md="12"
          ><ElFormItem label="IT 项目经理" prop="it_manager_ids"
            ><ProjectPersonSelect
              v-model="model.it_manager_ids"
              label="IT 项目经理"
              :initial-people="options.users"
              :selected-people="selectedPeople"
              :departments="options.departments" /></ElFormItem
        ></ElCol>
        <ElCol :xs="24" :md="12"
          ><ElFormItem label="是否对外采购" prop="external_purchase"
            ><ElRadioGroup v-model="model.external_purchase"
              ><ElRadio :value="true">是</ElRadio><ElRadio :value="false">否</ElRadio></ElRadioGroup
            ></ElFormItem
          ></ElCol
        >
        <ElCol :xs="24" :md="12"
          ><ElFormItem label="业务项目经理" prop="business_manager_ids"
            ><ProjectPersonSelect
              v-model="model.business_manager_ids"
              label="业务项目经理"
              :initial-people="options.users"
              :selected-people="selectedPeople"
              :departments="options.departments" /></ElFormItem
        ></ElCol>
        <ElCol :xs="24" :md="12"
          ><ElFormItem label="业务部门" prop="business_dept_id"
            ><ElTreeSelect
              v-model="model.business_dept_id"
              class="wf-full"
              :data="departments"
              :props="{ label: 'name', children: 'children' }"
              node-key="id"
              check-strictly
              filterable /></ElFormItem
        ></ElCol>
        <ElCol :xs="24" :md="12"
          ><ElFormItem label="币种" prop="currency"
            ><ElSelect v-model="model.currency" class="wf-full" filterable
              ><ElOption
                v-for="item in options.dictionaries.currency"
                :key="item.value"
                :label="item.label"
                :value="item.value" /></ElSelect></ElFormItem
        ></ElCol>
        <ElCol :xs="24" :md="12"
          ><ElFormItem label="计划开始日期" prop="planned_start_date"
            ><ElDatePicker
              v-model="model.planned_start_date"
              type="date"
              value-format="YYYY-MM-DD"
              class="wf-full" /></ElFormItem
        ></ElCol>
        <ElCol :xs="24" :md="12"
          ><ElFormItem label="计划结束日期" prop="planned_end_date"
            ><ElDatePicker
              v-model="model.planned_end_date"
              type="date"
              value-format="YYYY-MM-DD"
              class="wf-full" /></ElFormItem
        ></ElCol>
      </ElRow>
    </ElForm>
    <ProjectMilestones
      ref="milestonesRef"
      v-model="model.milestones"
      :initial-people="options.users"
      :selected-people="selectedPeople"
      :departments="options.departments"
      :disabled="disabled"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { FormInstance, FormRules } from "element-plus";
import ProjectPersonSelect from "./ProjectPersonSelect.vue";
import ProjectMilestones from "./ProjectMilestones.vue";
import {
  departmentTree,
  type ProjectFormData,
  type Options,
  type Person,
} from "@/api/module_workflow/workflow";
const model = defineModel<ProjectFormData>({ required: true });
const props = defineProps<{ options: Options; selectedPeople?: Person[]; disabled?: boolean }>();
const formRef = ref<FormInstance>();
const milestonesRef = ref<InstanceType<typeof ProjectMilestones>>();
const departments = computed(() => departmentTree(props.options.departments));
const missingDictionaries = computed(() =>
  ["initiation_type", "category", "currency"].some(
    (key) => !props.options.dictionaries[key]?.length
  )
);
const rules = computed<FormRules>(() =>
  Object.fromEntries(
    Object.keys(model.value)
      .filter((key) => !["attachment_ids", "milestones"].includes(key))
      .map((key) => [
        key,
        [
          { required: true, message: "请填写或选择此项", trigger: "change" },
          ...(key === "name"
            ? [{ whitespace: true, message: "项目名称不能全为空白", trigger: "blur" }]
            : []),
          ...(key === "planned_end_date"
            ? [
                {
                  validator: (_rule: unknown, value: string, callback: (error?: Error) => void) =>
                    callback(
                      value &&
                        model.value.planned_start_date &&
                        value < model.value.planned_start_date
                        ? new Error("结束日期不能早于开始日期")
                        : undefined
                    ),
                  trigger: "change",
                },
              ]
            : []),
        ],
      ])
  )
);
defineExpose({
  validate: async () => {
    if (milestonesRef.value?.validate() === false) return false;
    return formRef.value?.validate();
  },
});
</script>
