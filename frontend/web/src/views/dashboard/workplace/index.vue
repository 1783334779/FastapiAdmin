<template>
  <div class="flex flex-col relative last:mb-0">
    <ElRow :gutter="24">
      <ElCol :sm="12" :md="12" :lg="6" class="mb-4"><TotalOrderVolume /></ElCol>
      <ElCol :sm="12" :md="12" :lg="6" class="mb-4"><TotalProducts /></ElCol>
      <ElCol :sm="24" :md="12" :lg="6" class="mb-4"><ProductSales /></ElCol>
      <ElCol :sm="24" :md="12" :lg="6" class="mb-4"><SalesGrowth /></ElCol>
    </ElRow>

    <ElRow :gutter="24">
      <ElCol :span="24" class="mb-4"><CartConversionRate /></ElCol>
    </ElRow>

    <ElRow :gutter="24">
      <ElCol :sm="12" :md="12" :lg="6" class="mb-4"><SalesTrend /></ElCol>
      <ElCol :sm="12" :md="12" :lg="6" class="mb-4"><SalesClassification /></ElCol>
      <ElCol :sm="24" :md="12" :lg="6" class="mb-4"><HotCommodity /></ElCol>
      <ElCol :sm="24" :md="12" :lg="6" class="mb-4"><AnnualSales /></ElCol>
    </ElRow>

    <ElRow :gutter="24">
      <ElCol :sm="24" :md="12" :lg="12" class="mb-4"><ActiveUser /></ElCol>
      <ElCol :sm="24" :md="12" :lg="12" class="mb-4"><SalesOverview /></ElCol>
    </ElRow>
  </div>
</template>

<script setup lang="ts">
import ActiveUser from "./modules/active-user.vue";
import SalesOverview from "./modules/sales-overview.vue";
import TotalOrderVolume from "./modules/total-order-volume.vue";
import TotalProducts from "./modules/total-products.vue";
import SalesTrend from "./modules/sales-trend.vue";
import SalesClassification from "./modules/sales-classification.vue";
import HotCommodity from "./modules/hot-commodity.vue";
import AnnualSales from "./modules/annual-sales.vue";
import ProductSales from "./modules/product-sales.vue";
import SalesGrowth from "./modules/sales-growth.vue";
import CartConversionRate from "./modules/cart-conversion-rate.vue";

defineOptions({ name: "DashboardWorkplace" });
</script>
