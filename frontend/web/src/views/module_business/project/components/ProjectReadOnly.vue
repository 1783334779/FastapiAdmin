<template>
  <ElDescriptions :column="2" border class="wf-descriptions">
    <ElDescriptionsItem label="项目名称" :span="2">{{ data.name }}</ElDescriptionsItem>
    <ElDescriptionsItem label="立项类型">{{
      data.labels?.initiation_type ?? data.initiation_type
    }}</ElDescriptionsItem>
    <ElDescriptionsItem label="项目类别">{{
      data.labels?.category ?? data.category
    }}</ElDescriptionsItem>
    <ElDescriptionsItem label="IT 项目经理">{{ names(data.it_manager_ids) }}</ElDescriptionsItem>
    <ElDescriptionsItem label="是否对外采购">{{
      data.external_purchase === true ? "是" : "否"
    }}</ElDescriptionsItem>
    <ElDescriptionsItem label="业务项目经理">{{
      names(data.business_manager_ids)
    }}</ElDescriptionsItem>
    <ElDescriptionsItem label="业务部门">{{
      data.labels?.business_dept_id ?? data.business_dept_id
    }}</ElDescriptionsItem>
    <ElDescriptionsItem label="项目周期"
      >{{ data.planned_start_date }} 至 {{ data.planned_end_date }}</ElDescriptionsItem
    >
    <ElDescriptionsItem label="币种">{{
      data.labels?.currency ?? data.currency
    }}</ElDescriptionsItem>
    <ElDescriptionsItem label="创建人">{{
      data.creator_name ?? data.creator_user_id
    }}</ElDescriptionsItem>
    <ElDescriptionsItem label="创建部门快照">{{
      data.creator_dept_name ?? data.creator_dept_id
    }}</ElDescriptionsItem>
  </ElDescriptions>
</template>
<script setup lang="ts">
import type { ProjectSnapshot } from "@/api/module_workflow/workflow";
const props = defineProps<{ data: ProjectSnapshot }>();
function names(ids: number[] = []) {
  return ids
    .map((id) => props.data.users?.find((person) => person.id === id)?.name ?? `用户 ${id}`)
    .join("、");
}
</script>
