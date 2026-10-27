<template>
  <div v-loading="loading" class="fa-full-height wf-page">
    <ElResult v-if="loadError" icon="error" title="无法查看项目" :sub-title="loadError"
      ><template #extra><ElButton @click="load">重试</ElButton></template></ElResult
    >
    <template v-else-if="project">
      <section class="wf-section">
        <div class="wf-toolbar">
          <ElButton @click="router.push('/business/projects')">返回列表</ElButton
          ><FaStatusTag
            :type="statusType(project.status)"
            :label="statusLabels[project.status] ?? project.status"
          /><span class="wf-muted">资料 v{{ project.revision_no }}</span
          ><span class="wf-spacer" />
          <ElButton
            v-if="project.allowed_actions?.edit"
            v-hasPerm="['module_business:project:update']"
            @click="router.push(`/business/projects/${project.id}/edit`)"
            >编辑草稿</ElButton
          >
          <ElButton
            v-if="project.allowed_actions?.submit"
            v-hasPerm="['module_business:project:submit']"
            type="primary"
            :loading="busy"
            @click="submit"
            >提交审批</ElButton
          >
          <ElButton
            v-if="project.allowed_actions?.withdraw"
            v-hasPerm="['module_business:project:withdraw']"
            :loading="busy"
            @click="withdraw"
            >撤回</ElButton
          >
          <ElButton
            v-if="project.allowed_actions?.delete"
            v-hasPerm="['module_business:project:delete']"
            type="danger"
            plain
            :loading="busy"
            @click="remove"
            >删除草稿</ElButton
          >
          <ElButton @click="load">刷新</ElButton>
        </div>
        <div class="wf-toolbar">
          <ElSelect v-model="selectedRevision" aria-label="查看资料版本" style="width: 220px"
            ><ElOption
              v-for="revision in project.revisions"
              :key="revision.id"
              :value="revision.id"
              :label="`资料 v${revision.revision_no}${revision.id === project.revision_id ? '（当前）' : '（历史）'}`" /></ElSelect
          ><span class="wf-muted">审批记录保留原审阅版本，旧通过结果不会被改写。</span>
        </div>
        <ProjectReadOnly :data="shownSnapshot" />
      </section>
      <section v-if="project.workflow" class="wf-section">
        <div v-if="project.workflow.blocked" class="wf-toolbar">
          <ElButton v-hasPerm="['module_system:workflow:recover']" :loading="busy" @click="recover"
            >修复配置后重试恢复</ElButton
          >
        </div>
        <ApprovalHistory
          :history="project.workflow"
          :revisions="project.revisions ?? []"
          @view-revision="viewRevision"
        />
      </section>
      <section v-else class="wf-section wf-muted">
        尚未发起审批。提交时会检查全部分支的审批人，并绑定当时启用的发布版本。
      </section>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { projectApi } from "@/api/module_business/project";
import {
  workflowApi,
  statusLabels,
  statusType,
  type ProjectData,
  type ProjectSnapshot,
} from "@/api/module_workflow/workflow";
import ProjectReadOnly from "./components/ProjectReadOnly.vue";
import ApprovalHistory from "@/views/module_workflow/shared/ApprovalHistory.vue";
import "@/views/module_workflow/shared/workflow.scss";
const route = useRoute(),
  router = useRouter();
const project = ref<ProjectData>(),
  selectedRevision = ref<number>(),
  loading = ref(false),
  busy = ref(false),
  loadError = ref("");
const shownSnapshot = computed(
  () =>
    (project.value?.revisions?.find((item) => item.id === selectedRevision.value)?.payload ??
      project.value) as ProjectSnapshot
);
async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    project.value = await projectApi.detail(Number(route.params.id));
    selectedRevision.value = project.value.revision_id;
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : "请重试";
  } finally {
    loading.value = false;
  }
}
async function submit() {
  if (!project.value) return;
  busy.value = true;
  try {
    const check = await projectApi.precheck(project.value.id);
    if (!check.valid) {
      await ElMessageBox.alert(
        check.issues.map((item) => `${item.node_name}：${item.reason}`).join("\n"),
        "审批人员尚未配齐"
      );
      return;
    }
    await ElMessageBox.confirm(
      `确认按流程第 ${check.version_no} 版提交？提交后不能直接修改资料。`,
      "提交审批"
    );
    await projectApi.submit(project.value.id, project.value.lock_version);
    ElMessage.success("已提交");
    await load();
  } finally {
    busy.value = false;
  }
}
async function withdraw() {
  if (!project.value) return;
  await ElMessageBox.confirm("确认撤回到起草？只有尚无人作出审批操作才允许撤回。", "撤回项目");
  busy.value = true;
  try {
    await projectApi.withdraw(project.value.id, project.value.lock_version);
    ElMessage.success("已撤回");
    await load();
  } finally {
    busy.value = false;
  }
}
async function remove() {
  if (!project.value) return;
  await ElMessageBox.confirm("删除草稿会终止相关挂起流程，审批历史仍保留。确认删除？", "删除草稿", {
    type: "warning",
  });
  busy.value = true;
  try {
    await projectApi.remove(project.value.id, project.value.lock_version);
    ElMessage.success("草稿已删除");
    await router.push("/business/projects");
  } finally {
    busy.value = false;
  }
}
async function recover() {
  if (!project.value?.workflow) return;
  busy.value = true;
  try {
    await workflowApi.recover(project.value.workflow.id, project.value.workflow.lock_version);
    ElMessage.success("已执行恢复检查");
    await load();
  } finally {
    busy.value = false;
  }
}
function viewRevision(id: number) {
  selectedRevision.value = id;
  window.scrollTo({ top: 0, behavior: "smooth" });
}
onMounted(load);
watch(() => route.params.id, load);
</script>
