import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("@utils", () => ({ request: state.request }));
import { privateFileApi } from "@/api/module_common/private-file";

beforeEach(() => state.request.mockReset());
describe("通用私有文件接口契约", () => {
  it("上传使用独立multipart接口，不需要任何业务ID", async () => {
    const item = { id: 8, original_name: "资料.txt", size_bytes: 5, content_type: "text/plain" };
    state.request.mockResolvedValue({ data: { data: item } });
    const file = new File(["hello"], "资料.txt");
    const progress = vi.fn();
    expect(await privateFileApi.upload(file, progress)).toEqual(item);
    const config = state.request.mock.calls[0]![0];
    expect(config.url).toBe("/common/file/private/upload");
    expect(config.data).toBeInstanceOf(FormData);
    expect(config.data.get("file")).toBe(file);
    expect([...config.data.keys()]).toEqual(["file"]);
    config.onUploadProgress({ loaded: 100, total: 100 });
    expect(progress).toHaveBeenCalledWith(99);
  });

  it("业务上下文只作为下载鉴权输入，响应是Blob", async () => {
    const blob = new Blob(["private"]);
    state.request.mockResolvedValue({ data: blob });
    const context = { business_key: "example", business_id: 42 };
    expect(await privateFileApi.download(8, context)).toBe(blob);
    expect(state.request).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "/common/file/private/8/download",
        params: context,
        responseType: "blob",
      })
    );
  });
});
