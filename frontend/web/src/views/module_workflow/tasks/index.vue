<template>
  <div class="fa-full-height wf-page">
    <section class="wf-section">
      <div class="wf-toolbar">
        <ElTabs v-model="bucket" @tab-change="changeBucket"
          ><ElTabPane name="todo" label="我的待办" /><ElTabPane
            name="done"
            label="我的已办" /></ElTabs
        ><span class="wf-spacer" /><ElButton :loading="loading" @click="load">刷新</ElButton>
      </div>
      <ElAlert
        type="info"
        :closable="false"
        title="这里只展示自己的审批任务。能打开任务关联项目，不代表拥有该部门其他项目的查看权限。"
      />
      <ElTable v-loading="loading" :data="rows" row-key="id"
        ><ElTableColumn
          prop="project_name"
          label="项目名称"
          min-width="200"
          show-overflow-tooltip /><ElTableColumn
          prop="node_name"
          label="审批节点"
          min-width="160"
          show-overflow-tooltip /><ElTableColumn
          prop="round_no"
          label="轮次"
          width="80" /><ElTableColumn label="任务状态" width="120"
          ><template #default="{ row }"
            ><FaStatusTag
              :type="statusType(row.status)"
              :label="statusLabels[row.status] ?? row.status" /></template></ElTableColumn
        ><ElTableColumn label="流程状态" width="120"
          ><template #default="{ row }">{{
            statusLabels[row.workflow_status] ?? row.workflow_status
          }}</template></ElTableColumn
        ><ElTableColumn label="到达时间" width="150"
          ><template #default="{ row }">{{
            row.created_time?.slice(0, 16).replace("T", " ")
          }}</template></ElTableColumn
        ><ElTableColumn label="操作" width="180" fixed="right"
          ><template #default="{ row }"
            ><ElButton link @click="router.push(`/workflow/tasks/${row.id}`)">{{
              row.status === "PENDING" && row.workflow_status === "RUNNING" ? "办理" : "查看"
            }}</ElButton></template
          ></ElTableColumn
        ><template #empty
          ><ElEmpty
            :description="
              bucket === 'todo'
                ? '当前没有待办，流程进入审核节点后会在这里生成任务。'
                : '尚无已办记录。已关闭、已取消的任务会明确标注，不会显示成你已同意。'
            " /></template
      ></ElTable>
      <div class="wf-pagination">
        <ElPagination
          v-model:current-page="page"
          v-model:page-size="size"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="load"
          @size-change="changeBucket"
        />
      </div>
    </section>
  </div>
</template>
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  workflowApi,
  statusLabels,
  statusType,
  type TaskListRow,
} from "@/api/module_workflow/workflow";
import "@/views/module_workflow/shared/workflow.scss";
const router = useRouter(),
  bucket = ref("todo"),
  page = ref(1),
  size = ref(10),
  total = ref(0),
  loading = ref(false),
  rows = ref<TaskListRow[]>([]);
async function load() {
  loading.value = true;
  try {
    const result = await workflowApi.tasks(bucket.value, page.value, size.value);
    rows.value = result.items;
    total.value = result.total;
  } finally {
    loading.value = false;
  }
}
function changeBucket() {
  page.value = 1;
  void load();
}
onMounted(load);
</script>
