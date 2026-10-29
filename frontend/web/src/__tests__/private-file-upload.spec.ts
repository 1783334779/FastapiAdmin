import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { flushPromises, mount } from "@vue/test-utils";
import type { UploadRequestOptions } from "element-plus";

const state = vi.hoisted(() => ({
  options: vi.fn(),
  upload: vi.fn(),
  discard: vi.fn(),
  download: vi.fn(),
  saveAs: vi.fn(),
  warning: vi.fn(),
}));
vi.mock("@/api/module_common/private-file", () => ({
  privateFileApi: state,
  attachmentSize: (size: number) => `${size} bytes`,
}));
vi.mock("file-saver", () => ({ saveAs: state.saveAs }));
vi.mock("element-plus", () => ({ ElMessage: { warning: state.warning } }));
import Upload from "@/components/forms/fa-private-file-upload/index.vue";
import FileList from "@/components/media/fa-private-file-list/index.vue";

const Button = defineComponent({
  props: { disabled: Boolean },
  emits: ["click"],
  setup:
    (props, { slots, emit }) =>
    () =>
      h(
        "button",
        {
          disabled: props.disabled,
          onClick: () => {
            if (!props.disabled) emit("click");
          },
        },
        slots.default?.()
      ),
});
const Uploader = defineComponent({
  name: "ElUpload",
  props: ["httpRequest", "beforeUpload", "disabled"],
  setup:
    (_, { slots }) =>
    () =>
      h("div", slots.default?.()),
});
const stubs = { ElUpload: Uploader, ElButton: Button, ElAlert: true, FaSvgIcon: true };
const item = { id: 8, original_name: "资料.txt", size_bytes: 12, content_type: "text/plain" };
const file = () => Object.assign(new File(["hello"], "资料.txt"), { uid: Date.now() });
async function editor(props = {}) {
  const wrapper = mount(Upload, { props: { modelValue: [], ...props }, global: { stubs } });
  await flushPromises();
  return wrapper;
}
beforeEach(() => {
  Object.values(state).forEach((fn) => fn.mockReset());
  state.options.mockResolvedValue({
    max_file_size: 1024,
    extensions: [".txt"],
    temporary_hours: 24,
  });
  state.upload.mockResolvedValue(item);
});

describe("通用私有文件组件", () => {
  it("上传完成才提供文件ID，并在上传期间阻止业务保存", async () => {
    const wrapper = await editor();
    let finish!: (value: typeof item) => void;
    state.upload.mockImplementation((_file, progress) => {
      progress(50);
      return new Promise((resolve) => {
        finish = resolve;
      });
    });
    const uploading = wrapper.findComponent(Uploader).props("httpRequest")({
      file: file(),
    } as UploadRequestOptions);
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("上传中 50%");
    expect(wrapper.emitted("busy-change")?.at(-1)).toEqual([true]);
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
    finish(item);
    await uploading;
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([[8]]);
    expect(wrapper.emitted("busy-change")?.at(-1)).toEqual([false]);
  });

  it("失败保留重试入口，重复点击不会同时发出两次上传", async () => {
    const wrapper = await editor();
    state.upload.mockRejectedValueOnce(new Error("network"));
    await wrapper.findComponent(Uploader).props("httpRequest")({ file: file() });
    await flushPromises();
    expect(wrapper.text()).toContain("上传失败");
    expect(wrapper.emitted("busy-change")?.at(-1)).toEqual([true]);
    let finish!: (value: typeof item) => void;
    state.upload.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        })
    );
    const retry = wrapper.findAll("button").find((b) => b.text() === "重试")!;
    await retry.trigger("click");
    await retry.trigger("click");
    expect(state.upload).toHaveBeenCalledTimes(2);
    finish(item);
    await flushPromises();
    expect(wrapper.emitted("busy-change")?.at(-1)).toEqual([false]);
  });

  it("客户端检查空文件、类型和数量", async () => {
    const wrapper = await editor({ maxFiles: 1 });
    const before = wrapper.findComponent(Uploader).props("beforeUpload");
    expect(before(file())).toBe(true);
    expect(before(Object.assign(new File([], "empty.txt"), { uid: 3 }))).toBe(false);
    expect(before(Object.assign(new File(["bad"], "bad.exe"), { uid: 4 }))).toBe(false);
    await wrapper.setProps({ modelValue: [8] });
    expect(before(file())).toBe(false);
    await wrapper.findComponent(Uploader).props("httpRequest")({ file: file() });
    expect(state.upload).not.toHaveBeenCalled();
  });

  it("移除既有业务附件只更新关联，不调用临时文件废弃", async () => {
    const wrapper = await editor({ modelValue: [8], initialFiles: [item] });
    await wrapper
      .findAll("button")
      .find((b) => b.text() === "移除")!
      .trigger("click");
    await flushPromises();
    expect(state.discard).not.toHaveBeenCalled();
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([[]]);
  });

  it("业务不可写时不允许上传，既有文件仍可按业务权限下载", async () => {
    const context = { business_key: "example", business_id: 6 };
    const wrapper = await editor({
      modelValue: [8],
      initialFiles: [item],
      downloadContext: context,
      canUpload: false,
    });
    expect(wrapper.text()).toContain("当前业务不可创建或编辑");
    expect(state.options).not.toHaveBeenCalled();
    expect(wrapper.findComponent(Uploader).exists()).toBe(false);
    await wrapper
      .findAll("button")
      .find((b) => b.text() === "下载")!
      .trigger("click");
    expect(state.download).toHaveBeenCalledWith(8, context);
  });

  it("只读列表通过同一通用接口下载并保留原始文件名", async () => {
    const blob = new Blob(["private"]);
    state.download.mockResolvedValue(blob);
    const context = { business_key: "example", business_id: 9 };
    const wrapper = mount(FileList, {
      props: { items: [item], downloadContext: context },
      global: { stubs },
    });
    await wrapper.find("button").trigger("click");
    await flushPromises();
    expect(state.download).toHaveBeenCalledWith(8, context);
    expect(state.saveAs).toHaveBeenCalledWith(blob, item.original_name);
  });
});
