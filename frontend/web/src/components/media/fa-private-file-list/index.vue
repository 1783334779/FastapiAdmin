<template>
  <div v-if="items.length" class="private-file-stack">
    <div v-for="item in items" :key="item.id" class="private-file-row">
      <span class="attachment-name">{{ item.original_name }}</span>
      <span class="private-file-muted">{{ attachmentSize(item.size_bytes) }}</span>
      <ElButton link :loading="downloading === item.id" @click="download(item)">下载</ElButton>
    </div>
  </div>
  <span v-else class="private-file-muted">无附件</span>
</template>
<script setup lang="ts">
import { ref } from "vue";
import { saveAs } from "file-saver";
import {
  privateFileApi,
  attachmentSize,
  type PrivateFile,
  type FileDownloadContext,
} from "@/api/module_common/private-file";
const props = defineProps<{ items: PrivateFile[]; downloadContext?: FileDownloadContext }>();
const downloading = ref<number>();
async function download(item: PrivateFile) {
  downloading.value = item.id;
  try {
    saveAs(await privateFileApi.download(item.id, props.downloadContext), item.original_name);
  } finally {
    downloading.value = undefined;
  }
}
</script>
<style scoped>
.private-file-stack {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.private-file-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.private-file-muted {
  color: var(--el-text-color-secondary);
}

.attachment-name {
  overflow-wrap: anywhere;
}
</style>
