<!-- 节日 / 公告顶栏：文案来自 festival 配置（占位符 {{version}}、{{introduceUrl}}） -->
<template>
  <div :class="{ 'mb-5': showFestivalStrip }">
    <Transition name="festival-strip">
      <FaTextScroll
        v-if="showFestivalStrip"
        type="theme"
        :text="festivalScrollDisplayHtml"
        height="40px"
        :speed="55"
        :always-scroll="true"
      />
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useCeremony } from "@/hooks/core/useCeremony";
import { WEB_LINKS } from "@utils";

defineOptions({ name: "FaFestivalTextScroll" });

const { currentFestivalData } = useCeremony();

function versionLabel(): string {
  const v = String(import.meta.env.VITE_VERSION ?? "").trim();
  if (!v) return "";
  return v.startsWith("v") ? v : `v${v}`;
}

const festivalScrollDisplayHtml = computed(() => {
  const raw = currentFestivalData.value?.scrollText ?? "";
  const ver = versionLabel() || "v0.0.0";
  return raw.replace(/\{\{version\}\}/g, ver).replace(/\{\{introduceUrl\}\}/g, WEB_LINKS.INTRODUCE);
});

/** 通告横幅常驻：只要有通告文本就展示，不提供关闭入口 */
const showFestivalStrip = computed(
  () => !!currentFestivalData.value?.scrollText && currentFestivalData.value.scrollText !== ""
);
</script>
