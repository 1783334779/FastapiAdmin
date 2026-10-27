<template>
  <div class="wf-stack">
    <div class="wf-inline">
      <FaStatusTag
        :type="statusType(history.status)"
        :label="statusLabels[history.status] ?? history.status"
      /><span>流程第 {{ history.version_no }} 版 · 第 {{ history.round_no }} 轮</span>
    </div>
    <ElAlert
      v-if="history.blocked"
      type="warning"
      :closable="false"
      :title="`流程阻塞：${history.blocked.reason}`"
    />
    <ElAlert
      v-if="history.returns.length"
      type="info"
      :closable="false"
      title="正在定点返回处理，其他未完成审批已暂停"
      :description="
        history.returns
          .map((item) => `目标 ${nodeName(item.target)}，处理后返回 ${nodeName(item.origin_node)}`)
          .join('；')
      "
    />
    <WorkflowPreview :graph="history.graph" :visits="history.visits" />
    <ElTable :data="history.visits" row-key="id" :default-expand-all="false">
      <ElTableColumn type="expand"
        ><template #default="{ row }"
          ><div class="history-expanded">
            <div class="wf-muted">
              审批模式：{{
                row.approval_mode === "ALL" ? "全部通过" : "任意一人通过"
              }}；本次名单进入后固定。
            </div>
            <ElTable :data="row.tasks" size="small"
              ><ElTableColumn label="审批人"
                ><template #default="scope">{{
                  personName(row as Visit, scope.row.assignee_id)
                }}</template></ElTableColumn
              ><ElTableColumn label="结果"
                ><template #default="scope"
                  ><FaStatusTag
                    :type="statusType(scope.row.status)"
                    :label="
                      statusLabels[scope.row.status] ?? scope.row.status
                    " /></template></ElTableColumn
              ><ElTableColumn prop="opinion" label="意见" show-overflow-tooltip /><ElTableColumn
                label="审阅资料"
                ><template #default="scope"
                  ><ElButton
                    v-if="scope.row.decision_revision_id"
                    link
                    @click="emit('viewRevision', scope.row.decision_revision_id)"
                    >{{ revisionName(scope.row.decision_revision_id) }}</ElButton
                  ><span v-else>尚未操作</span></template
                ></ElTableColumn
              ></ElTable
            >
            <div v-for="source in row.resolution" :key="source.source" class="wf-muted">
              {{ source.source }}：{{
                source.user_ids.map((id: number) => personName(row as Visit, id)).join("、") ||
                "无人"
              }}<span v-if="source.departments_checked.length"
                >（查找部门：{{ source.departments_checked.join(" → ") }}）</span
              >
            </div>
          </div></template
        ></ElTableColumn
      >
      <ElTableColumn prop="round_no" label="轮次" width="80" />
      <ElTableColumn prop="node_name" label="审批节点" min-width="160" show-overflow-tooltip />
      <ElTableColumn label="状态" width="120"
        ><template #default="{ row }"
          ><FaStatusTag
            :type="statusType(row.status)"
            :label="statusLabels[row.status] ?? row.status" /></template
      ></ElTableColumn>
      <ElTableColumn label="进入时资料" width="150"
        ><template #default="{ row }"
          ><ElButton link @click="emit('viewRevision', row.revision_id)">{{
            revisionName(row.revision_id)
          }}</ElButton></template
        ></ElTableColumn
      >
    </ElTable>
    <ElDivider content-position="left">流程操作记录</ElDivider>
    <ElTimeline>
      <ElTimelineItem
        v-for="action in history.actions"
        :key="action.id"
        :timestamp="action.created_time"
      >
        <div>
          {{ action.actor_name ?? `用户 ${action.actor_id}` }} ·
          {{ actionLabels[action.action] ?? action.action }}
        </div>
        <div v-if="action.opinion" class="wf-muted">{{ action.opinion }}</div>
        <div v-if="action.details.mode" class="wf-muted">
          {{
            action.details.mode === "RESTART"
              ? "驳回重走，从开始重新审批"
              : `定点返回：${nodeName(String(action.details.target))}`
          }}
        </div>
        <div v-if="action.details.reason" class="wf-muted">{{ action.details.reason }}</div>
        <div v-if="action.details.target_node" class="wf-muted">
          选择路线 → {{ nodeName(String(action.details.target_node)) }}
        </div>
        <div v-if="action.details.round_no" class="wf-muted">
          第 {{ action.details.round_no }} 轮
        </div>
        <ElButton link @click="emit('viewRevision', action.revision_id)">{{
          revisionName(action.revision_id)
        }}</ElButton>
      </ElTimelineItem>
    </ElTimeline>
  </div>
</template>
<script setup lang="ts">
import {
  statusLabels,
  statusType,
  type WorkflowHistory,
  type Visit,
  type Revision,
} from "@/api/module_workflow/workflow";
import WorkflowPreview from "./WorkflowPreview.vue";
const props = defineProps<{ history: WorkflowHistory; revisions: Revision[] }>();
const emit = defineEmits<{ viewRevision: [id: number] }>();
const actionLabels: Record<string, string> = {
  SUBMIT: "提交审批",
  ENTER: "进入审核节点",
  APPROVE: "审批通过",
  REJECT: "驳回",
  FINISH: "流程完成",
  BLOCKED: "流程阻塞",
  RECOVER: "重试恢复",
  RESUBMIT_TARGETED: "定点返回后重新提交",
  WITHDRAW: "创建人撤回",
  NEW_ROUND: "关闭旧待办并开始新一轮",
  DELETE_DRAFT: "删除草稿并终止流程",
  ROUTE: "条件选路",
  FORK: "启动并行分支",
  JOIN: "并行分支全部汇合",
};
function nodeName(key: string) {
  return key === "DRAFT"
    ? "起草"
    : (props.history.graph.nodes.find((node) => node.id === key)?.data.label ?? key);
}
function personName(visit: Visit, id: number) {
  return visit.candidates.find((person) => person.id === id)?.name ?? `用户 ${id}`;
}
function revisionName(id: number) {
  return `资料 v${props.revisions.find((item) => item.id === id)?.revision_no ?? id}`;
}
</script>
<style scoped>
.history-expanded {
  padding: 16px;
}
</style>
