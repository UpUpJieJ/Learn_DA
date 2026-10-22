<script setup lang="ts">
import { RouterView } from "vue-router";
import { onMounted } from "vue";
import Navbar from "@/components/layout/Navbar.vue";
import ToastHost from "@/components/ui/ToastHost.vue";
import { useLearnerStateStore } from "@/stores/learnerState";

// 阶段 1：启动时从服务器同步学习进度（统一学习事实）
const learnerStateStore = useLearnerStateStore();
onMounted(() => {
    learnerStateStore.syncFromServer();
});
</script>

<template>
    <div id="app" class="flex min-h-screen flex-col">
        <Navbar />

        <main class="min-h-0 flex-1">
            <RouterView v-slot="{ Component, route }">
                <Transition name="fade" mode="out-in">
                    <component :is="Component" :key="route.path" class="flex-1" />
                </Transition>
            </RouterView>
        </main>

        <!-- 瞬时反馈（useToast）唯一渲染点 -->
        <ToastHost />
    </div>
</template>

<style scoped>
/* 页面切换淡入淡出 */
.fade-enter-active,
.fade-leave-active {
    transition: opacity 0.15s ease;
}

.fade-enter-from,
.fade-leave-to {
    opacity: 0;
}
</style>