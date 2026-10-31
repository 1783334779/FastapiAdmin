import {
  http,
  command,
  type ProjectData,
  type ProjectFormData,
  type Page,
  type Options,
} from "@/api/module_workflow/workflow";
import { request } from "@utils";

export interface ProjectListFilters {
  name: string;
  status: string;
}

function projectPayload(body: ProjectFormData): ProjectFormData {
  if (body.milestones === undefined) return { ...body };
  return {
    ...body,
    // 详情可能附带只读 ID 等字段，写请求只发送后端输入 Schema 接受的五个字段。
    milestones: body.milestones.map((item) => ({
      name: item.name,
      delivery_standard: item.delivery_standard,
      owner_user_ids: [...new Set(item.owner_user_ids)],
      planned_start_time: item.planned_start_time,
      planned_end_time: item.planned_end_time,
    })),
  };
}

export const projectApi = {
  list: (params: Record<string, unknown>) =>
    http<Page<ProjectData>>("/business/project/list", "get", undefined, params),
  export: async ({ name, status }: ProjectListFilters) => {
    const response = await request<Blob>({
      url: "/business/project/export",
      method: "get",
      params: { name, status },
      responseType: "blob",
      timeout: 120000,
    });
    return response.data;
  },
  detail: (id: number) => http<ProjectData>(`/business/project/detail/${id}`),
  create: (body: ProjectFormData) =>
    http<ProjectData>("/business/project/create", "post", projectPayload(body)),
  createAndSubmit: (body: ProjectFormData, key: string) =>
    http<ProjectData>("/business/project/create-and-submit", "post", {
      ...projectPayload(body),
      command_key: key,
    }),
  update: (id: number, body: ProjectFormData, version: number) =>
    http<ProjectData>(`/business/project/update/${id}`, "put", {
      ...projectPayload(body),
      expected_version: version,
    }),
  updateAndSubmit: (id: number, body: ProjectFormData, version: number, key: string) =>
    http<ProjectData>(`/business/project/update-and-submit/${id}`, "put", {
      ...projectPayload(body),
      expected_version: version,
      command_key: key,
    }),
  options: (search = "") =>
    http<Options>("/business/project/options", "get", undefined, { search }),
  precheck: (id: number) =>
    http<{ valid: boolean; issues: { node_name: string; reason: string }[]; version_no: number }>(
      `/business/project/${id}/precheck`,
      "post"
    ),
  submit: (id: number, version: number) =>
    http(`/business/project/${id}/submit`, "post", command(version)),
  withdraw: (id: number, version: number) =>
    http(`/business/project/${id}/withdraw`, "post", command(version)),
  remove: (id: number, version: number) =>
    http(`/business/project/${id}/delete`, "post", command(version)),
};

export function emptyProject(): ProjectFormData {
  return {
    name: "",
    initiation_type: "",
    category: "",
    it_manager_ids: [],
    external_purchase: undefined,
    business_manager_ids: [],
    business_dept_id: undefined,
    planned_start_date: "",
    planned_end_date: "",
    currency: "",
    attachment_ids: [],
    milestones: [],
  };
}
