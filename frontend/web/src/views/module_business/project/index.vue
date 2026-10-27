<template>
  <div class="fa-full-height wf-page">
    <FaSearchBar
      v-model="search"
      :items="searchItems"
      :show-expand="false"
      :is-expand="true"
      @search="searchNow"
      @reset="reset"
    />
    <ElCard class="fa-table-card" shadow="never">
      <div class="wf-toolbar">
        <ElButton
          v-hasPerm="['module_business:project:create']"
          type="primary"
          @click="router.push('/business/projects/new')"
          ><FaSvgIcon icon="ri:add-line" />新建项目</ElButton
        ><ElButton @click="router.push('/workflow/tasks')">我的审批</ElButton
        ><span class="wf-spacer" /><ElButton :loading="loading" @click="load">刷新</ElButton>
      </div>
      <ElTable v-loading="loading" :data="rows" row-key="id">
        <ElTableColumn prop="name" label="项目名称" min-width="200" show-overflow-tooltip />
        <ElTableColumn label="立项类型" min-width="120" show-overflow-tooltip
          ><template #default="{ row }">{{
            row.labels?.initiation_type ?? row.initiation_type
          }}</template></ElTableColumn
        >
        <ElTableColumn label="业务部门" min-width="120" show-overflow-tooltip
          ><template #default="{ row }">{{
            row.labels?.business_dept_id ?? row.business_dept_id
          }}</template></ElTableColumn
        >
        <ElTableColumn label="状态" width="120"
          ><template #default="{ row }"
            ><FaStatusTag
              :type="statusType(row.status)"
              :label="statusLabels[row.status] ?? row.status" /></template
        ></ElTableColumn>
        <ElTableColumn prop="creator_name" label="创建人" width="110" show-overflow-tooltip />
        <ElTableColumn label="创建日期" width="120"
          ><template #default="{ row }">{{
            row.created_time?.slice(0, 10)
          }}</template></ElTableColumn
        >
        <ElTableColumn label="操作" fixed="right" width="180"
          ><template #default="{ row }"
            ><ElButton
              v-hasPerm="['module_business:project:detail']"
              link
              @click="router.push(`/business/projects/${row.id}`)"
              >详情</ElButton
            ><ElButton
              v-if="row.allowed_actions?.edit"
              v-hasPerm="['module_business:project:update']"
              link
              @click="router.push(`/business/projects/${row.id}/edit`)"
              >编辑</ElButton
            ></template
          ></ElTableColumn
        >
        <template #empty
          ><ElEmpty
            description="暂无可见项目。创建人可查看自己的项目，负责人可查看管理部门及下级部门项目。"
            ><ElButton
              v-hasPerm="['module_business:project:create']"
              @click="router.push('/business/projects/new')"
              >新建项目</ElButton
            ></ElEmpty
          ></template
        >
      </ElTable>
      <div class="wf-pagination">
        <ElPagination
          v-model:current-page="page"
          v-model:page-size="size"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="load"
          @size-change="searchNow"
        />
      </div>
    </ElCard>
  </div>
</template>
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { projectApi } from "@/api/module_business/project";
import { statusLabels, statusType, type ProjectData } from "@/api/module_workflow/workflow";
import "@/views/module_workflow/shared/workflow.scss";
const router = useRouter();
const search = ref<Record<string, string>>({ name: "", status: "" });
const searchItems = [
  { key: "name", label: "项目名称", type: "input", props: { clearable: true } },
  {
    key: "status",
    label: "项目状态",
    type: "select",
    props: {
      clearable: true,
      options: ["DRAFT", "IN_REVIEW", "RETURNED", "BLOCKED", "APPROVED", "WITHDRAWN"].map(
        (value) => ({ value, label: statusLabels[value] })
      ),
    },
  },
];
const rows = ref<ProjectData[]>([]),
  total = ref(0),
  page = ref(1),
  size = ref(10),
  loading = ref(false);
async function load() {
  loading.value = true;
  try {
    const result = await projectApi.list({
      ...search.value,
      page_no: page.value,
      page_size: size.value,
    });
    rows.value = result.items;
    total.value = result.total;
  } finally {
    loading.value = false;
  }
}
function searchNow() {
  page.value = 1;
  void load();
}
function reset() {
  search.value = { name: "", status: "" };
  searchNow();
}
onMounted(load);
</script>
