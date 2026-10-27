import { beforeEach, describe, expect, it, vi } from "vitest";

const { request } = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("@utils", () => ({ request }));
import {
  command,
  departmentTree,
  http,
  statusType,
  workflowApi,
} from "@/api/module_workflow/workflow";
import { emptyProject, projectApi } from "@/api/module_business/project";
import { isPersonalWorkflowPath } from "@/router/workflow-access";

beforeEach(() => request.mockReset());

describe("项目与审批 API 契约", () => {
  it("解开 Axios response + 业务响应两层，不把 envelope 当成流程数组", async () => {
    const definitions = [{ id: 1, name: "流程" }];
    request.mockResolvedValue({ data: { code: 0, msg: "成功", data: definitions } });
    expect(await workflowApi.list()).toEqual(definitions);
  });

  it("正确保留 false、空列表及空值", async () => {
    for (const value of [false, [], null]) {
      request.mockResolvedValue({ data: { data: value } });
      expect(await http("/test")).toEqual(value);
    }
  });

  it("审批携带资料版本与并发版本，不修改调用方数据", async () => {
    request.mockResolvedValue({ data: { data: { status: "RUNNING" } } });
    const body = { ...command(7), expected_revision_id: 12, opinion: "同意" };
    await workflowApi.decide(5, "approve", body);
    expect(request).toHaveBeenCalledWith({
      url: "/workflow/task/5/approve",
      method: "post",
      data: body,
      params: undefined,
    });
    expect(body.expected_version).toBe(7);
  });

  it("项目经理多选与否采购值原样发送", async () => {
    request.mockResolvedValue({ data: { data: { id: 9 } } });
    const body = { ...emptyProject(), external_purchase: false, it_manager_ids: [2, 3] };
    await projectApi.create(body);
    expect(request.mock.calls[0]?.[0].data).toMatchObject({
      external_purchase: false,
      it_manager_ids: [2, 3],
    });
  });

  it("每次不同业务命令生成不同幂等键", () => {
    expect(command(1).command_key).not.toEqual(command(1).command_key);
    expect(command(3).expected_version).toBe(3);
  });
});

describe("审批页面辅助数据", () => {
  it("只放行个人待办精确路径，不扩大到流程配置或项目列表", () => {
    expect(isPersonalWorkflowPath("/workflow/tasks")).toBe(true);
    expect(isPersonalWorkflowPath("/workflow/tasks/12")).toBe(true);
    for (const path of [
      "/workflow",
      "/workflow/tasks/12/recover",
      "/system/approval-flows",
      "/business/projects",
      "/workflow/tasks-other",
    ]) {
      expect(isPersonalWorkflowPath(path)).toBe(false);
    }
  });
  it("部门树保留缺失父节点的有效部门，且不修改输入", () => {
    const departments = [
      { id: 1, name: "集团", parent_id: null },
      { id: 2, name: "财务", parent_id: 1 },
      { id: 3, name: "独立", parent_id: 99 },
    ];
    const tree = departmentTree(departments);
    expect(tree.map((item) => item.id)).toEqual([1, 3]);
    expect(tree[0]?.children?.[0]?.id).toBe(2);
    expect(departments[0]).not.toHaveProperty("children");
  });

  it("已通过、阻塞和暂停不混用颜色状态", () => {
    expect(statusType("APPROVED")).toBe("success");
    expect(statusType("BLOCKED")).toBe("warning");
    expect(statusType("SUSPENDED")).toBe("warning");
    expect(statusType("PENDING")).toBe("primary");
  });
});
