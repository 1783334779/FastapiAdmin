<template>
  <ElTag :type="type" :size="size" :effect="effect" :round="round" :closable="closable">
    {{ displayLabel }}
  </ElTag>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";

defineOptions({ name: "FaStatusTag" });

const { t, te } = useI18n();

const STATUS_KEYS: Record<string, string> = {
  启用: "common.enabled",
  停用: "common.disabled",
  成功: "common.success",
  失败: "common.failed",
  是: "common.yes",
  否: "common.no",
  男: "common.male",
  女: "common.female",
  草稿: "common.draft",
  已发布: "common.published",
  已回滚: "common.rolledBack",
  未知: "common.unknown",
};

interface Props {
  /** 显示文本 */
  label?: string | number;
  /**
   * 标签类型（与 EP ElTag 一致）。
   * 不传时为 EP 默认样式（无 type 属性）。
   */
  type?: "primary" | "success" | "warning" | "danger" | "info";
  /** 尺寸 */
  size?: "large" | "default" | "small";
  /** 主题效果：light（默认）/ dark / plain */
  effect?: "light" | "dark" | "plain";
  /** 是否圆角 */
  round?: boolean;
  /** 是否可关闭 */
  closable?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  label: "",
  type: undefined,
  size: undefined,
  effect: "light",
  round: false,
  closable: false,
});

const displayLabel = computed(() => {
  const text = String(props.label ?? "");
  const key = STATUS_KEYS[text];
  return key && te(key) ? t(key) : text;
});
</script>
