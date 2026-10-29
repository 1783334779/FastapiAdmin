import { request } from "@utils";
export interface PrivateFile {
  id: number;
  original_name: string;
  size_bytes: number;
  content_type: string;
}
export interface FileDownloadContext {
  business_key?: string;
  business_id?: number;
  revision_id?: number;
  task_id?: number;
}
const path = "/common/file/private";
export interface AttachmentLimits {
  max_file_size: number;
  extensions: string[];
  temporary_hours: number;
}
export const privateFileApi = {
  options: async () => {
    const result = await request<{ data: AttachmentLimits }>({
      url: `${path}/options`,
      method: "get",
    });
    return result.data.data;
  },
  upload: async (file: File, progress?: (percent: number) => void) => {
    const data = new FormData();
    data.append("file", file);
    const response = await request<{ data: PrivateFile }>({
      url: `${path}/upload`,
      method: "post",
      data,
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 120000,
      onUploadProgress: ({ loaded, total }) => {
        if (total) progress?.(Math.min(99, Math.round((loaded * 100) / total)));
      },
    });
    return response.data.data;
  },
  discard: async (id: number) => {
    await request({ url: `${path}/${id}/discard`, method: "post" });
  },
  download: async (id: number, context: FileDownloadContext = {}) => {
    const response = await request<Blob>({
      url: `${path}/${id}/download`,
      method: "get",
      params: context,
      responseType: "blob",
      timeout: 120000,
    });
    return response.data;
  },
};

export function attachmentSize(bytes: number): string {
  return bytes >= 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    : `${Math.max(1, Math.ceil(bytes / 1024))} KB`;
}
