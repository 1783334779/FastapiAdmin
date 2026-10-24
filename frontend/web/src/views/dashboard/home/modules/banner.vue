<template>
  <ElCarousel height="220px" :interval="6000">
    <ElCarouselItem>
      <FaBasicBanner
        height="100%"
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
          <ElIcon v-else :size="40" class="text-g-500"><UserFilled /></ElIcon>
          <div>
            <div class="text-base font-semibold text-g-800">{{ currentUser.name }}</div>
            <div class="text-xs text-g-600">
              {{ currentUser.dept_name }} · {{ currentUser.description }} ·
              {{ currentUser.last_login }}
            </div>
          </div>
        </div>
      </FaBasicBanner>
    </ElCarouselItem>

    <ElCarouselItem>
      <FaBasicBanner
        height="100%"
        title="Web · H5 · 小程序，一套全栈"
        subtitle="FastAPI + Vue3 + TypeScript，前后端类型共享；200+ REST 接口开箱即用，设计系统三端一致。"
        boxStyle="bg-theme/10!"
        titleColor="var(--fa-gray-900)"
        subtitleColor="var(--fa-gray-500)"
        :decoration="false"
        :buttonConfig="{
          show: true,
          text: '开始探索',
          color: 'var(--fa-brand-blue, var(--theme-color))',
          textColor: '#fff',
          radius: '8px',
        }"
        @buttonClick="handleBannerClick"
      />
    </ElCarouselItem>
  </ElCarousel>
</template>

<script setup lang="ts">
import { useRouter } from "vue-router";
import { computed } from "vue";
import bannerCover from "@imgs/login/lf_icon2.webp";
import { useUserStore } from "@stores";
import { greetings } from "@utils";
import { UserFilled } from "@element-plus/icons-vue";

const userStore = useUserStore();

const userInfo = computed(() => userStore.basicInfo);

const router = useRouter();

const handleBannerClick = (): void => {
  router.push("/dashboard/analysis");
};

const timefix = greetings();
const welcome = "祝你开心每一天！";
const currentUser = {
  avatar: userStore.basicInfo.avatar || "",
  name: userInfo.value.name || "吴彦祖",
  username: userInfo.value.username || "账号信息",
  description: userInfo.value.description || "用户说明",
  dept_name: userInfo.value.dept_name || "软件专业部",
  last_login: userInfo.value.last_login || "2023-01-01 00:00:00",
};

const bannerTitle = `欢迎回来 ～ ${currentUser.name}（${currentUser.username}） ${timefix} ${welcome}`;

const bannerSubtitle = `基于 FastAPI + Vue3 + TypeScript 构建的企业级中后台解决方案，支持多端开发。`;
</script>

<style scoped>
:deep(.basic-banner__title) {
  font-size: 22px;
  line-height: 1.4;
}

@media (width <= 1440px) {
  :deep(.basic-banner__background-image) {
    display: none;
  }
}
</style>
