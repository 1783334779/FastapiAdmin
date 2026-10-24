<template>
  <FaBasicBanner
    height="220px"
    :title="bannerTitle"
    :subtitle="bannerSubtitle"
    boxStyle="bg-theme/10!"
    titleColor="var(--fa-gray-900)"
    subtitleColor="var(--fa-gray-500)"
    :decoration="false"
    :meteorConfig="{
      enabled: true,
      count: 10,
    }"
    :buttonConfig="{
      show: false,
      text: '开始探索',
      color: 'var(--fa-success)',
      textColor: '#fff',
      radius: '6px',
    }"
    :imageConfig="{
      src: bannerCover,
      width: '18rem',
      bottom: '-7.5rem',
    }"
    @click="handleBannerClick"
  >
    <div class="flex items-center gap-3 mt-2">
      <ElAvatar
        v-if="currentUser.avatar"
        :size="44"
        :src="currentUser.avatar"
        style="background-color: transparent"
      />
      <ElIcon v-else :size="40" class="text-g-500"><FaSvgIcon icon="ri:user-3-line" /></ElIcon>
      <div>
        <div class="text-base font-semibold text-g-800">{{ currentUser.name }}</div>
        <div class="text-xs text-g-600">
          {{ currentUser.dept_name }} · {{ currentUser.description }} ·
          {{ currentUser.last_login }}
        </div>
      </div>
    </div>
  </FaBasicBanner>
</template>

<script setup lang="ts">
import { useRouter } from "vue-router";
import { computed } from "vue";
import bannerCover from "@imgs/login/lf_icon2.webp";
import { useUserStore } from "@stores";
import { greetings } from "@utils";

const userStore = useUserStore();

const userInfo = computed(() => userStore.basicInfo);

const router = useRouter();

const handleBannerClick = (): void => {
  router.push("/dashboard/analysis");
};

const timefix = greetings();
const currentUser = {
  avatar: userStore.basicInfo.avatar || "",
  name: userInfo.value.name || "吴彦祖",
  username: userInfo.value.username || "账号信息",
  description: userInfo.value.description || "用户说明",
  dept_name: userInfo.value.dept_name || "软件专业部",
  last_login: userInfo.value.last_login || "2023-01-01 00:00:00",
};

const bannerTitle = `${timefix.replace(/[！!]$/, "")}，${currentUser.name}`;

const bannerSubtitle = `基于 FastAPI + Vue3 + TypeScript 构建的企业级中后台解决方案，支持多端开发。`;
</script>

<style scoped>
:deep(.basic-banner__title) {
  font-size: 22px;
  line-height: 1.4;
}

/* 窄屏横幅空间不足时隐藏插画，只保留文案，避免压字 */
@media (width <= 1440px) {
  :deep(.basic-banner__background-image) {
    display: none;
  }
}
</style>
