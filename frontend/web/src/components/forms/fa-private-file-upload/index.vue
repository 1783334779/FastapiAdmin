<template>
  <div class="private-file-stack">
    <ElAlert v-if="loadError" type="error" :closable="false" title="附件配置加载失败">
      <ElButton link @click="loadLimits">重试</ElButton>
    </ElAlert>
    <div class="private-file-row">
      <span>{{ label }}</span>
      <ElUpload
        v-if="limits && canUpload"
        multiple
        :show-file-list="false"
        :accept="limits.extensions.join(',')"
        :disabled="disabled || count >= maxFiles"
        :before-upload="beforeUpload"
        :http-request="upload"
      >
        <ElButton :disabled="disabled || count >= maxFiles">
          <FaSvgIcon icon="ri:attachment-line" />上传附件
        </ElButton>
      </ElUpload>
      <span v-if="limits" class="private-file-muted">
        可选，最多 {{ maxFiles }} 个，每个不超过
        {{ attachmentSize(limits.max_file_size) }}；未保存附件
        {{ limits.temporary_hours }} 小时后过期。
      </span>
      <span v-if="!canUpload" class="private-file-muted"
        >当前业务不可创建或编辑，不能添加附件。</span
      >
    </div>
    <div v-for="item in selected" :key="item.id" class="private-file-row">
      <span class="attachment-name">{{ item.original_name }}</span>
      <span class="private-file-muted">{{ attachmentSize(item.size_bytes) }}</span>
      <ElButton link :loading="downloading === item.id" @click="download(item)">下载</ElButton>
      <ElButton link type="danger" :disabled="disabled || removing" @click="remove(item)"
        >移除</ElButton
      >
    </div>
    <div v-for="entry in pending" :key="entry.uid" class="private-file-row">
      <span class="attachment-name">{{ entry.file.name }}</span>
      <span>{{
        entry.status === "uploading" ? `上传中 ${entry.percent}%` : "上传失败，请重试或移除"
      }}</span>
      <ElButton v-if="entry.status === 'error'" link :disabled="disabled" @click="run(entry)"
        >重试</ElButton
      >
      <ElButton
        v-if="entry.status === 'error'"
        link
        type="danger"
        :disabled="disabled"
        @click="drop(entry.uid)"
        >移除</ElButton
      >
    </div>
    <span v-if="!selected.length && !pending.length" class="private-file-muted">暂未添加附件</span>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage, type UploadRawFile, type UploadRequestOptions } from "element-plus";
import { saveAs } from "file-saver";
import {
  privateFileApi,
  attachmentSize,
  type AttachmentLimits,
  type PrivateFile,
  type FileDownloadContext,
} from "@/api/module_common/private-file";

const model = defineModel<number[]>({ default: () => [] });
const props = withDefaults(
  defineProps<{
    initialFiles?: PrivateFile[];
    disabled?: boolean;
    maxFiles?: number;
    label?: string;
    downloadContext?: FileDownloadContext;
    canUpload?: boolean;
  }>(),
  { maxFiles: 20, label: "附件", canUpload: true }
);
const emit = defineEmits<{ "busy-change": [value: boolean] }>();
interface Pending {
  uid: number;
  file: File;
  status: "uploading" | "error";
  percent: number;
}
const limits = ref<AttachmentLimits>(),
  loadError = ref(false);
const cache = ref<Record<number, PrivateFile>>({});
const pending = ref<Pending[]>([]),
  removing = ref(false),
  downloading = ref<number>();
const initialIds = computed(() => new Set((props.initialFiles ?? []).map((item) => item.id)));
watch(
  () => props.initialFiles,
  (items) => {
    for (const item of items ?? []) cache.value[item.id] = item;
  },
  { immediate: true }
);
const selected = computed(() =>
  model.value.map((id) => cache.value[id]).filter((item): item is PrivateFile => !!item)
);
const count = computed(() => model.value.length + pending.value.length);
watch(
  () => pending.value.length > 0 || removing.value,
  (busy) => emit("busy-change", busy),
  { flush: "sync" }
);
async function loadLimits() {
  if (!props.canUpload) return;
  loadError.value = false;
  try {
    limits.value = await privateFileApi.options();
  } catch {
    loadError.value = true;
  }
}
function beforeUpload(file: UploadRawFile) {
  if (!props.canUpload || !limits.value || props.disabled || count.value >= props.maxFiles) {
    ElMessage.warning("附件数量已达上限或当前无法上传");
    return false;
  }
  if (file.size > limits.value.max_file_size || file.size === 0) {
    ElMessage.warning(`请选择非空且不超过 ${attachmentSize(limits.value.max_file_size)} 的文件`);
    return false;
  }
  const extension = "." + (file.name.split(".").pop() ?? "").toLowerCase();
  if (!limits.value.extensions.includes(extension)) {
    ElMessage.warning("不支持该附件类型");
    return false;
  }
  return true;
}
async function upload(options: UploadRequestOptions) {
  // beforeUpload 可能批量异步完成，发请求前再次计算剩余名额。
  if (!props.canUpload || !limits.value || count.value >= props.maxFiles || props.disabled) {
    ElMessage.warning("附件数量已达上限");
    return;
  }
  const entry: Pending = { uid: options.file.uid, file: options.file, percent: 0, status: "error" };
  pending.value.push(entry);
  await run(pending.value[pending.value.length - 1]!);
}
async function run(entry: Pending) {
  if (!props.canUpload || props.disabled || entry.status === "uploading") return;
  entry.status = "uploading";
  entry.percent = 0;
  try {
    const item = await privateFileApi.upload(entry.file, (percent) => {
      entry.percent = percent;
    });
    cache.value[item.id] = item;
    model.value = [...model.value, item.id];
    drop(entry.uid);
  } catch {
    entry.status = "error";
  }
}
function drop(uid: number) {
  pending.value = pending.value.filter((entry) => entry.uid !== uid);
}
async function remove(item: PrivateFile) {
  if (props.disabled || removing.value) return;
  removing.value = true;
  try {
    if (!initialIds.value.has(item.id)) await privateFileApi.discard(item.id);
    model.value = model.value.filter((id) => id !== item.id);
  } finally {
    removing.value = false;
  }
}
async function download(item: PrivateFile) {
  downloading.value = item.id;
  try {
    saveAs(await privateFileApi.download(item.id, props.downloadContext), item.original_name);
  } finally {
    downloading.value = undefined;
  }
}
onMounted(loadLimits);
</script>
<style scoped>
.private-file-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.private-file-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  min-width: 0;
}

.private-file-muted {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.attachment-name {
  overflow-wrap: anywhere;
}
</style>
