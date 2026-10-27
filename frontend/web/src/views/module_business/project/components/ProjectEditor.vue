<template>
  <div v-loading="loading" class="fa-full-height wf-page">
    <ElResult v-if="loadError" icon="error" title="项目资料加载失败" :sub-title="loadError"
      ><template #extra><ElButton @click="load">重试</ElButton></template></ElResult
    >
    <section v-else class="wf-section">
      <div class="wf-toolbar">
        <ElButton @click="router.push('/business/projects')">返回列表</ElButton
        ><span class="wf-muted">{{
          projectId
            ? "只有创建人可以编辑，可保存草稿或保存并提交审批"
            : "可保存草稿稍后处理，也可直接提交审批"
        }}</span
        ><span class="wf-spacer" /><ElButton
          v-if="canSubmit"
          type="primary"
          :loading="activeAction === 'submit'"
          :disabled="loading || !!activeAction"
          @click="save('submit')"
          >提交审批</ElButton
        ><ElButton
          :loading="activeAction === 'draft'"
          :disabled="loading || !!activeAction"
          @click="save('draft')"
          >保存草稿</ElButton
        >
      </div>
      <ProjectForm
        ref="formRef"
        v-model="form"
        :options="options"
        :selected-people="selectedPeople"
      />
    </section>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { emptyProject, projectApi } from "@/api/module_business/project";
import type { Options, Person, ProjectFormData } from "@/api/module_workflow/workflow";
import ProjectForm from "./ProjectForm.vue";
import { useAuth } from "@/hooks/core/useAuth";
import "@/views/module_workflow/shared/workflow.scss";
const props = defineProps<{ projectId?: number }>();
const router = useRouter();
const { hasAuth } = useAuth();
const canSubmit = computed(
  () =>
    hasAuth("module_business:project:submit") &&
    hasAuth(`module_business:project:${props.projectId ? "update" : "create"}`)
);
const form = ref(emptyProject());
const formRef = ref<InstanceType<typeof ProjectForm>>();
const options = ref<Options>({ users: [], departments: [], dictionaries: {} });
const selectedPeople = ref<Person[]>([]);
const loading = ref(false),
  activeAction = ref<"draft" | "submit">(),
  loadError = ref("");
const version = ref(1);
let submitCommand: { fingerprint: string; key: string } | undefined;
async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    options.value = await projectApi.options();
    if (props.projectId) {
      const detail = await projectApi.detail(props.projectId);
      if (!detail.allowed_actions?.edit) throw new Error("当前账号或项目状态不允许编辑");
      form.value = Object.fromEntries(
        Object.keys(emptyProject()).map((key) => [key, detail[key as keyof ProjectFormData]])
      ) as unknown as ProjectFormData;
      selectedPeople.value = detail.users ?? [];
      version.value = detail.lock_version;
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : "请稍后重试";
  } finally {
    loading.value = false;
  }
}
async function save(action: "draft" | "submit") {
  if (activeAction.value || loading.value) return;
  if (action === "submit" && !canSubmit.value) return;
  activeAction.value = action;
  try {
    try {
      if (!(await formRef.value?.validate())) return;
    } catch {
      return;
    }
    let result;
    if (action === "submit") {
      const confirmed = await ElMessageBox.confirm(
        "确认提交审批？系统将校验所有节点的审批人，通过后直接发起流程。",
        "提交审批"
      ).then(
        () => true,
        () => false
      );
      if (!confirmed) return;
      // 请求超时可能已经成功；同一份表单重试继续使用原键，不能重复创建项目。
      const fingerprint = JSON.stringify([props.projectId, version.value, form.value]);
      if (submitCommand?.fingerprint !== fingerprint)
        submitCommand = { fingerprint, key: crypto.randomUUID() };
      result = props.projectId
        ? await projectApi.updateAndSubmit(
            props.projectId,
            form.value,
            version.value,
            submitCommand.key
          )
        : await projectApi.createAndSubmit(form.value, submitCommand.key);
      if (result.status === "BLOCKED")
        ElMessage.warning("项目已提交，流程暂时阻塞，请查看详情中的原因");
      else ElMessage.success("项目已提交审批");
    } else {
      result = props.projectId
        ? await projectApi.update(props.projectId, form.value, version.value)
        : await projectApi.create(form.value);
      ElMessage.success("草稿已保存");
    }
    await router.push(`/business/projects/${result.id}`);
  } finally {
    activeAction.value = undefined;
  }
}
onMounted(load);
</script>
