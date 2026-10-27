import {
  http,
  command,
  type ProjectData,
  type ProjectFormData,
  type Page,
  type Options,
} from "@/api/module_workflow/workflow";

export const projectApi = {
  list: (params: Record<string, unknown>) =>
    http<Page<ProjectData>>("/business/project/list", "get", undefined, params),
  detail: (id: number) => http<ProjectData>(`/business/project/detail/${id}`),
  create: (body: ProjectFormData) => http<ProjectData>("/business/project/create", "post", body),
  createAndSubmit: (body: ProjectFormData, key: string) =>
    http<ProjectData>("/business/project/create-and-submit", "post", { ...body, command_key: key }),
  update: (id: number, body: ProjectFormData, version: number) =>
    http<ProjectData>(`/business/project/update/${id}`, "put", {
      ...body,
      expected_version: version,
    }),
  updateAndSubmit: (id: number, body: ProjectFormData, version: number, key: string) =>
    http<ProjectData>(`/business/project/update-and-submit/${id}`, "put", {
      ...body,
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
  };
}
