<template>
  <div v-loading="loading" class="fa-full-height wf-page">
    <ElResult v-if="loadError" icon="error" title="任务无法打开" :sub-title="loadError"
      ><template #extra><ElButton @click="load">重试</ElButton></template></ElResult
    >
    <template v-else-if="detail">
      <section class="wf-section">
        <div class="wf-toolbar">
          <ElButton @click="router.push('/workflow/tasks')">返回我的审批</ElButton
          ><span>{{ detail.task.node_name }}</span
          ><FaStatusTag
            :type="statusType(detail.task.status)"
            :label="statusLabels[detail.task.status] ?? detail.task.status"
          /><span class="wf-spacer" /><ElButton @click="load">刷新</ElButton>
        </div>
        <ElAlert
          v-if="detail.task.activation_revision_id !== detail.project.revision_id"
          type="warning"
          :closable="false"
          title="任务生成后项目资料发生过修改，请核对最新资料及历史审批对应版本。"
        />
        <div class="wf-toolbar">
          <ElSelect v-model="selectedRevision" aria-label="查看项目资料版本" style="width: 220px"
            ><ElOption
              v-for="revision in detail.revisions"
              :key="revision.id"
              :value="revision.id"
              :label="`资料 v${revision.revision_no}${revision.id === detail.project.revision_id ? '（当前）' : '（历史）'}`" /></ElSelect
          ><ElButton v-if="historical" link @click="selectedRevision = detail.project.revision_id"
            >回到当前资料后审批</ElButton
          >
        </div>
        <ProjectReadOnly
          :data="shownSnapshot"
          :project-id="detail.project.id"
          :revision-id="selectedRevision"
          :task-id="detail.task.id"
        />
        <ElForm v-if="detail.allowed_actions.approve" label-position="top" style="margin-top: 16px"
          ><ElFormItem label="审批意见"
            ><ElInput
              v-model="opinion"
              type="textarea"
              :rows="3"
              maxlength="2000"
              show-word-limit
              placeholder="通过意见可选，驳回必须填写原因" /></ElFormItem
        ></ElForm>
        <div v-if="detail.allowed_actions.approve" class="wf-toolbar">
          <ElButton type="primary" :loading="busy" :disabled="historical" @click="approve"
            >同意</ElButton
          ><ElButton
            type="danger"
            plain
            :disabled="historical || busy"
            @click="rejectVisible = true"
            >驳回</ElButton
          >
        </div>
        <ElAlert
          v-else
          type="info"
          :closable="false"
          title="当前任务已完成、暂停或流程已终止，只能查看。"
        />
      </section>
      <section class="wf-section">
        <ApprovalHistory
          :history="detail.workflow"
          :revisions="detail.revisions"
          @view-revision="(id) => (selectedRevision = id)"
        />
      </section>
    </template>
    <ElDrawer v-model="rejectVisible" title="驳回项目" size="520px" :close-on-click-modal="false"
      ><ElForm label-position="top"
        ><ElFormItem label="驳回模式"
          ><ElRadioGroup v-model="rejectMode"
            ><ElRadio value="RESTART">驳回重走</ElRadio
            ><ElRadio value="TARGETED">定点返回</ElRadio></ElRadioGroup
          ></ElFormItem
        ><ElAlert
          :closable="false"
          type="info"
          :title="
            rejectMode === 'RESTART'
              ? '回到起草，重新提交后固定从流程入口重走。'
              : '目标处理后直接回到当前驳回环节，不能跨并行分支。'
          " /><ElFormItem v-if="rejectMode === 'TARGETED'" label="退回目标"
          ><ElSelect v-model="rejectTarget" class="wf-full"
            ><ElOption
              v-for="target in detail?.reject_targets"
              :key="target.id"
              :value="target.id"
              :label="target.name" /></ElSelect></ElFormItem
        ><ElFormItem label="驳回原因" required
          ><ElInput
            v-model="opinion"
            type="textarea"
            :rows="4"
            maxlength="2000"
            show-word-limit /></ElFormItem></ElForm
      ><template #footer
        ><ElButton @click="rejectVisible = false">取消</ElButton
        ><ElButton type="danger" :loading="busy" @click="reject">确认驳回</ElButton></template
      ></ElDrawer
    >
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  command,
  workflowApi,
  statusLabels,
  statusType,
  type TaskDetail,
  type ProjectSnapshot,
} from "@/api/module_workflow/workflow";
import ProjectReadOnly from "./components/ProjectReadOnly.vue";
import ApprovalHistory from "@/views/module_workflow/shared/ApprovalHistory.vue";
import "@/views/module_workflow/shared/workflow.scss";
const route = useRoute(),
  router = useRouter();
const detail = ref<TaskDetail>(),
  selectedRevision = ref<number>(),
  opinion = ref(""),
  loading = ref(false),
  busy = ref(false),
  loadError = ref("");
const rejectVisible = ref(false),
  rejectMode = ref<"RESTART" | "TARGETED">("RESTART"),
  rejectTarget = ref("DRAFT");
const historical = computed(() => selectedRevision.value !== detail.value?.project.revision_id);
const shownSnapshot = computed(
  () =>
    (detail.value?.revisions.find((item) => item.id === selectedRevision.value)?.payload ??
      detail.value?.project) as ProjectSnapshot
);
async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    detail.value = await workflowApi.task(Number(route.params.taskId));
    selectedRevision.value = detail.value.project.revision_id;
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : "请重试";
  } finally {
    loading.value = false;
  }
}
async function decide(action: "approve" | "reject") {
  if (!detail.value || historical.value) return;
  busy.value = true;
  try {
    const payload = {
      ...command(detail.value.workflow.lock_version),
      expected_revision_id: detail.value.project.revision_id,
      opinion: opinion.value,
      ...(action === "reject"
        ? {
            mode: rejectMode.value,
            ...(rejectMode.value === "TARGETED" ? { target: rejectTarget.value } : {}),
          }
        : {}),
    };
    await workflowApi.decide(detail.value.task.id, action, payload);
    rejectVisible.value = false;
    opinion.value = "";
    ElMessage.success(action === "approve" ? "审批已记录" : "已驳回");
    await load();
  } finally {
    busy.value = false;
  }
}
async function approve() {
  await ElMessageBox.confirm("确认已审阅当前版本资料并同意？", "审批确认");
  await decide("approve");
}
async function reject() {
  if (!opinion.value.trim()) {
    ElMessage.warning("请填写驳回原因");
    return;
  }
  await decide("reject");
}
onMounted(load);
watch(() => route.params.taskId, load);
</script>
