<template>
  <ProjectEditor :key="String(route.params.id)" :project-id="Number(route.params.id)" />
</template>
<script setup lang="ts">
import { useRoute } from "vue-router";
import ProjectEditor from "./components/ProjectEditor.vue";
const route = useRoute();
</script>
