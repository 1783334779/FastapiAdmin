import { request } from "@utils";

export type StatusType = "primary" | "success" | "warning" | "danger" | "info";
export interface Person {
  id: number;
  name: string;
  username?: string;
  dept_id?: number;
}
export interface Department {
  id: number;
  name: string;
  parent_id?: number | null;
  children?: Department[];
}
export interface SystemRole {
  id: number;
  name: string;
  code: string;
}
export interface BusinessRole {
  id: number;
  code: string;
  name: string;
  strategy: "FIELD_USERS" | "DEPT_MANAGER";
  config: { field?: string; role_id?: number };
  enabled: boolean;
}
export interface Condition {
  logic?: "AND" | "OR";
  items?: Condition[];
  field?: string;
  op?: string;
  value?: string | number | boolean | (string | number | boolean)[];
}
export interface AssigneeRule {
  type: "SYSTEM_ROLE" | "BUSINESS_ROLE";
  role_id?: number;
  code?: string;
}
export interface GraphNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: {
    label: string;
    approval_mode?: "ANY" | "ALL";
    assignees?: AssigneeRule[];
    join_key?: string;
  };
}
export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  priority?: number;
  is_default?: boolean;
  condition?: Condition;
  label?: string;
}
export interface WorkflowGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}
export interface FlowDefinition {
  id: number;
  code: string;
  name: string;
  enabled: boolean;
  lock_version: number;
  published_version_id?: number;
  graph?: WorkflowGraph;
  read_only?: boolean;
  versions?: { id: number; version_no: number; created_time: string }[];
}
export interface ProjectFormData {
  name: string;
  initiation_type: string;
  category: string;
  it_manager_ids: number[];
  external_purchase: boolean | undefined;
  business_manager_ids: number[];
  business_dept_id: number | undefined;
  planned_start_date: string;
  planned_end_date: string;
  currency: string;
}
export interface ProjectSnapshot extends ProjectFormData {
  labels?: Record<string, string>;
  users?: Person[];
  creator_name?: string;
  creator_dept_name?: string;
  creator_user_id?: number;
  creator_dept_id?: number;
}
export interface Revision {
  id: number;
  revision_no: number;
  payload: ProjectSnapshot;
  created_time: string;
}
export interface ApprovalTask {
  id: number;
  assignee_id: number;
  status: string;
  opinion: string;
  decision_revision_id?: number;
  completed_time?: string;
}
export interface Visit {
  id: number;
  node_key: string;
  node_name: string;
  round_no: number;
  status: string;
  approval_mode: string;
  revision_id: number;
  candidates: Person[];
  resolution: { source: string; user_ids: number[]; departments_checked: number[] }[];
  tasks: ApprovalTask[];
}
export interface WorkflowHistory {
  id: number;
  status: string;
  round_no: number;
  version_id: number;
  version_no: number;
  lock_version: number;
  has_approval_action: boolean;
  graph: WorkflowGraph;
  blocked?: { reason: string; node_key: string };
  returns: { id: string; origin_node: string; target: string; phase: string }[];
  visits: Visit[];
  actions: {
    id: number;
    actor_id: number;
    actor_name?: string;
    action: string;
    revision_id: number;
    opinion: string;
    details: Record<string, unknown>;
    created_time: string;
  }[];
}
export interface ProjectData extends ProjectSnapshot {
  id: number;
  status: string;
  revision_id: number;
  revision_no: number;
  lock_version: number;
  created_time?: string;
  updated_time?: string;
  allowed_actions?: Record<string, boolean>;
  workflow?: WorkflowHistory | null;
  revisions?: Revision[];
}
export interface TaskDetail {
  task: { id: number; status: string; node_name: string; activation_revision_id: number };
  project: ProjectData;
  workflow: WorkflowHistory;
  allowed_actions: { approve: boolean; reject: boolean };
  reject_targets: { id: string; name: string }[];
  revisions: Revision[];
}
export interface TaskListRow {
  id: number;
  project_id: number;
  project_name: string;
  node_name: string;
  status: string;
  workflow_status: string;
  round_no: number;
  created_time: string;
  completed_time?: string;
}
export interface Page<T> {
  items: T[];
  total: number;
  page_no: number;
  page_size: number;
}
export interface Options {
  users: Person[];
  departments: Department[];
  dictionaries: Record<string, { value: string; label: string }[]>;
  roles?: SystemRole[];
  business_roles?: BusinessRole[];
}

export async function http<T>(
  url: string,
  method: "get" | "post" | "put" = "get",
  data?: unknown,
  params?: Record<string, unknown>
): Promise<T> {
  const result = await request<ApiResponse<T>>({ url, method, data, params });
  return result.data.data as T;
}
export const command = (version: number) => ({
  command_key: crypto.randomUUID(),
  expected_version: version,
});
export const workflowApi = {
  list: () => http<FlowDefinition[]>("/system/workflow/list"),
  detail: (id: number, versionId?: number) =>
    http<FlowDefinition>(
      `/system/workflow/detail/${id}`,
      "get",
      undefined,
      versionId ? { version_id: versionId } : undefined
    ),
  save: (data: unknown, id?: number) =>
    http<FlowDefinition>(
      id ? `/system/workflow/update/${id}` : "/system/workflow/create",
      id ? "put" : "post",
      data
    ),
  validate: (data: unknown) =>
    http<{ valid: boolean; issues: string[] }>("/system/workflow/validate", "post", data),
  publish: (id: number, version: number) =>
    http<FlowDefinition>(`/system/workflow/publish/${id}`, "post", command(version)),
  binding: () =>
    http<{ definition_id?: number; manager_role_id?: number }>("/system/workflow/binding"),
  bind: (data: unknown) => http("/system/workflow/binding", "put", data),
  options: () => http<Options>("/system/workflow/options"),
  roles: () => http<BusinessRole[]>("/system/workflow/business-roles"),
  saveRole: (data: unknown, id?: number) =>
    http(
      id ? `/system/workflow/business-roles/${id}` : "/system/workflow/business-roles",
      id ? "put" : "post",
      data
    ),
  members: (role: number) =>
    http<(Person & { managed_dept_ids: number[] })[]>(`/system/workflow/role-members/${role}`),
  saveScope: (role: number, user: number, ids: number[]) =>
    http(`/system/workflow/role-members/${role}/${user}`, "put", { dept_ids: ids }),
  tasks: (bucket: string, page: number, size: number) =>
    http<Page<TaskListRow>>(`/workflow/task/${bucket}`, "get", undefined, {
      page_no: page,
      page_size: size,
    }),
  task: (id: number) => http<TaskDetail>(`/workflow/task/${id}/detail`),
  decide: (id: number, action: string, data: unknown) =>
    http(`/workflow/task/${id}/${action}`, "post", data),
  recover: (id: number, version: number) =>
    http(`/workflow/task/instances/${id}/recover`, "post", command(version)),
};

export const statusLabels: Record<string, string> = {
  DRAFT: "起草",
  IN_REVIEW: "审批中",
  RUNNING: "运行中",
  RETURNED: "退回起草",
  BLOCKED: "流程阻塞",
  APPROVED: "已通过",
  WITHDRAWN: "已撤回",
  TERMINATED: "已终止",
  DELETED: "已删除",
  PENDING: "待处理",
  SUSPENDED: "已暂停",
  REJECTED: "已驳回",
  CLOSED: "已关闭",
  CANCELLED: "已取消",
  ACTIVE: "处理中",
};
export function statusType(status: string): StatusType {
  return status === "APPROVED"
    ? "success"
    : ["REJECTED", "TERMINATED", "DELETED"].includes(status)
      ? "danger"
      : ["BLOCKED", "RETURNED", "SUSPENDED"].includes(status)
        ? "warning"
        : ["IN_REVIEW", "RUNNING", "PENDING", "ACTIVE"].includes(status)
          ? "primary"
          : "info";
}
export function departmentTree(departments: Department[]): Department[] {
  const nodes = new Map(
    departments.map((item) => [item.id, { ...item, children: [] as Department[] }])
  );
  const roots: Department[] = [];
  nodes.forEach((item) => {
    const parent = item.parent_id ? nodes.get(item.parent_id) : undefined;
    if (parent && parent.id !== item.id) parent.children.push(item);
    else roots.push(item);
  });
  return roots;
}
