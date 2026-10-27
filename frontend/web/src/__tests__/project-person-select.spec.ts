import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import { mount } from "@vue/test-utils";

const { lookup } = vi.hoisted(() => ({ lookup: vi.fn() }));
vi.mock("@/api/module_business/project", () => ({ projectApi: { options: lookup } }));
import ProjectPersonSelect from "@/views/module_business/project/components/ProjectPersonSelect.vue";
import type { Person } from "@/api/module_workflow/workflow";

const SelectStub = defineComponent({
  props: ["modelValue", "remoteMethod", "loading", "noDataText"],
  emits: ["update:modelValue"],
  setup:
    (_props, { slots }) =>
    () =>
      h("div", slots.default?.()),
});
const OptionStub = defineComponent({
  props: ["value", "label"],
  setup:
    (props, { slots }) =>
    () =>
      h("div", { "data-user-id": props.value, "data-label": props.label }, slots.default?.()),
});
const people: Person[] = [
  { id: 11, name: "张三", username: "zhangsan_it", dept_id: 1 },
  { id: 22, name: "张三", username: "zhangsan_business", dept_id: 2 },
];
function createSelector(selected: number[] = []) {
  return mount(ProjectPersonSelect, {
    props: {
      modelValue: selected,
      label: "IT 项目经理",
      initialPeople: people,
      departments: [
        { id: 1, name: "技术部" },
        { id: 2, name: "财务部" },
      ],
    },
    global: { stubs: { ElSelect: SelectStub, ElOption: OptionStub } },
  });
}
beforeEach(() => lookup.mockReset());

describe("项目经理选择具体人员", () => {
  it("同名人员显示不同账号与部门，不展示角色名称", () => {
    const wrapper = createSelector();
    expect(wrapper.text()).toContain("张三（zhangsan_it）");
    expect(wrapper.text()).toContain("张三（zhangsan_business）");
    expect(wrapper.text()).toContain("技术部");
    expect(wrapper.text()).toContain("财务部");
    expect(wrapper.find('[data-user-id="11"]').exists()).toBe(true);
  });

  it("多选回传用户 ID 数组，而非名称/角色编码", async () => {
    const wrapper = createSelector();
    wrapper.getComponent(SelectStub).vm.$emit("update:modelValue", [11, 22]);
    await nextTick();
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual([[11, 22]]);
  });

  it("按账号筛选，只显示匹配结果，同时保留已选标签", async () => {
    const wrapper = createSelector([22]);
    lookup.mockResolvedValue({ users: [people[0]] });
    await wrapper.getComponent(SelectStub).props("remoteMethod")("zhangsan_it");
    expect(lookup).toHaveBeenCalledWith("zhangsan_it");
    expect(wrapper.find('[data-user-id="11"]').isVisible()).toBe(true);
    expect(wrapper.find('[data-user-id="22"]').isVisible()).toBe(false);
    expect(wrapper.find('[data-user-id="22"]').attributes("data-label")).toBe(
      "张三（zhangsan_business）"
    );
  });

  it("旧的慢请求不能覆盖新的搜索结果", async () => {
    const wrapper = createSelector();
    let finishOld!: (value: { users: Person[] }) => void;
    lookup.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishOld = resolve;
        })
    );
    lookup.mockResolvedValueOnce({ users: [people[1]] });
    const search = wrapper.getComponent(SelectStub).props("remoteMethod");
    const old = search("it");
    await search("business");
    finishOld({ users: [people[0]!] });
    await old;
    expect(wrapper.find('[data-user-id="22"]').exists()).toBe(true);
    expect(wrapper.find('[data-user-id="11"]').exists()).toBe(false);
  });

  it("两个经理选择器的查询状态互相独立", async () => {
    const itSelector = createSelector();
    const businessSelector = createSelector();
    lookup.mockResolvedValue({ users: [people[0]] });
    await itSelector.getComponent(SelectStub).props("remoteMethod")("zhangsan_it");
    expect(businessSelector.find('[data-user-id="22"]').isVisible()).toBe(true);
  });

  it("搜索失败可提示并重新搜索", async () => {
    const wrapper = createSelector();
    lookup.mockRejectedValueOnce(new Error("temporary failure"));
    const search = wrapper.getComponent(SelectStub).props("remoteMethod");
    await search("zhangsan_it");
    expect(wrapper.getComponent(SelectStub).props("noDataText")).toContain("加载失败");
    lookup.mockResolvedValue({ users: [people[0]] });
    await search("zhangsan_it");
    expect(wrapper.find('[data-user-id="11"]').isVisible()).toBe(true);
  });
});
