import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { flushPromises, mount } from "@vue/test-utils";

const state = vi.hoisted(() => ({
  create: vi.fn(),
  createAndSubmit: vi.fn(),
  update: vi.fn(),
  updateAndSubmit: vi.fn(),
  options: vi.fn(),
  detail: vi.fn(),
  push: vi.fn(),
  confirm: vi.fn(),
  validate: vi.fn(),
  hasAuth: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
}));
const blank = vi.hoisted(() => () => ({
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
}));
vi.mock("vue-router", () => ({ useRouter: () => ({ push: state.push }) }));
vi.mock("@/hooks/core/useAuth", () => ({ useAuth: () => ({ hasAuth: state.hasAuth }) }));
vi.mock("element-plus", () => ({
  ElMessage: { success: state.success, warning: state.warning },
  ElMessageBox: { confirm: state.confirm },
}));
vi.mock("@/api/module_business/project", () => ({ emptyProject: blank, projectApi: state }));
vi.mock("@/views/module_business/project/components/ProjectForm.vue", () => ({
  default: {
    name: "ProjectFormStub",
    props: ["modelValue"],
    emits: ["update:modelValue"],
    setup: (_: unknown, { expose }: { expose: (value: unknown) => void }) => {
      expose({ validate: state.validate });
      return () => null;
    },
  },
}));
import ProjectEditor from "@/views/module_business/project/components/ProjectEditor.vue";

const ButtonStub = defineComponent({
  props: { disabled: Boolean, loading: Boolean },
  emits: ["click"],
  setup:
    (props, { slots, emit }) =>
    () =>
      h(
        "button",
        {
          disabled: props.disabled || props.loading,
          onClick: () => {
            if (!props.disabled && !props.loading) emit("click");
          },
        },
        slots.default?.()
      ),
});
async function editor(id?: number) {
  const wrapper = mount(ProjectEditor, {
    props: id ? { projectId: id } : {},
    global: {
      stubs: { ElButton: ButtonStub, ElResult: true },
      directives: { loading: () => {} },
      config: { errorHandler: state.error },
    },
  });
  await flushPromises();
  return wrapper;
}
type Editor = Awaited<ReturnType<typeof editor>>;
function button(wrapper: Editor, label: string) {
  const found = wrapper.findAll("button").find((item) => item.text() === label);
  if (!found) throw new Error(`missing button: ${label}`);
  return found;
}
beforeEach(() => {
  Object.values(state).forEach((fn) => fn.mockReset());
  state.options.mockResolvedValue({ users: [], departments: [], dictionaries: {} });
  state.detail.mockResolvedValue({
    ...blank(),
    id: 9,
    lock_version: 3,
    allowed_actions: { edit: true },
    users: [],
  });
  state.create.mockResolvedValue({ id: 9, status: "DRAFT" });
  state.createAndSubmit.mockResolvedValue({ id: 9, status: "IN_REVIEW" });
  state.update.mockResolvedValue({ id: 9, status: "DRAFT" });
  state.updateAndSubmit.mockResolvedValue({ id: 9, status: "IN_REVIEW" });
  state.validate.mockResolvedValue(true);
  state.confirm.mockResolvedValue("confirm");
  state.hasAuth.mockReturnValue(true);
});

describe("项目表单保存或直接提交", () => {
  it("保存草稿只创建草稿，不自动提交", async () => {
    const wrapper = await editor();
    await button(wrapper, "保存草稿").trigger("click");
    await flushPromises();
    expect(state.create).toHaveBeenCalledOnce();
    expect(state.createAndSubmit).not.toHaveBeenCalled();
    expect(state.confirm).not.toHaveBeenCalled();
    expect(state.push).toHaveBeenCalledWith("/business/projects/9");
  });

  it("创建页提交只调用原子接口，不先调用保存草稿", async () => {
    const wrapper = await editor();
    await button(wrapper, "提交审批").trigger("click");
    await flushPromises();
    expect(state.createAndSubmit).toHaveBeenCalledWith(blank(), expect.any(String));
    expect(state.create).not.toHaveBeenCalled();
    expect(state.push).toHaveBeenCalledWith("/business/projects/9");
  });

  it("编辑页直接提交携带当前并发版本", async () => {
    const wrapper = await editor(9);
    await button(wrapper, "提交审批").trigger("click");
    await flushPromises();
    expect(state.updateAndSubmit).toHaveBeenCalledWith(9, blank(), 3, expect.any(String));
    expect(state.update).not.toHaveBeenCalled();
  });

  it("表单校验失败不请求任何写接口", async () => {
    state.validate.mockResolvedValue(false);
    const wrapper = await editor();
    await button(wrapper, "提交审批").trigger("click");
    await flushPromises();
    expect(state.createAndSubmit).not.toHaveBeenCalled();
    expect(state.confirm).not.toHaveBeenCalled();
  });

  it("取消提交确认不创建项目", async () => {
    state.confirm.mockRejectedValue("cancel");
    const wrapper = await editor();
    await button(wrapper, "提交审批").trigger("click");
    await flushPromises();
    expect(state.createAndSubmit).not.toHaveBeenCalled();
    expect(state.push).not.toHaveBeenCalled();
  });

  it("没有提交权限时只保留保存草稿", async () => {
    state.hasAuth.mockImplementation(
      (permission: string) => permission !== "module_business:project:submit"
    );
    const wrapper = await editor();
    expect(wrapper.findAll("button").map((item) => item.text())).not.toContain("提交审批");
    expect(button(wrapper, "保存草稿").exists()).toBe(true);
  });

  it("超时后的同内容重试沿用幂等键，不调用草稿接口", async () => {
    state.createAndSubmit.mockRejectedValueOnce(new Error("timeout"));
    const wrapper = await editor();
    await button(wrapper, "提交审批").trigger("click");
    await flushPromises();
    expect(state.push).not.toHaveBeenCalled();
    await button(wrapper, "提交审批").trigger("click");
    await flushPromises();
    expect(state.createAndSubmit.mock.calls[0]?.[1]).toBe(state.createAndSubmit.mock.calls[1]?.[1]);
    expect(state.create).not.toHaveBeenCalled();
  });

  it("提交尚未返回时禁用两个按钮，防止重复保存", async () => {
    let finish!: (value: unknown) => void;
    state.createAndSubmit.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        })
    );
    const wrapper = await editor();
    await button(wrapper, "提交审批").trigger("click");
    await flushPromises();
    expect(button(wrapper, "保存草稿").attributes("disabled")).toBeDefined();
    expect(button(wrapper, "提交审批").attributes("disabled")).toBeDefined();
    finish({ id: 9, status: "IN_REVIEW" });
    await flushPromises();
    expect(state.createAndSubmit).toHaveBeenCalledOnce();
  });
});
