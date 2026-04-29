<script setup lang="ts">
import { RouterView, useRoute } from "vue-router";
import { computed } from "vue";
import Navbar from "@/components/layout/Navbar.vue";

const route = useRoute();
const isPlayground = computed(() => route.path.startsWith("/playground"));
</script>

<template>
    <div
        id="app"
        class="flex flex-col"
        :class="
            isPlayground
                ? 'h-screen overflow-hidden bg-[#0d1117]'
                : 'min-h-screen'
        "
    >
        <!-- 顶部导航栏（Playground 页面内部自带 header，Navbar 会自动隐藏） -->
        <Navbar />

        <!-- 路由视图 -->
        <main
            class="flex-1 min-h-0"
            :class="isPlayground ? 'overflow-hidden' : ''"
        >
            <RouterView v-slot="{ Component, route }">
                <Transition name="fade" mode="out-in">
                    <KeepAlive :include="['Learning', 'Playground']">
                        <component
                            :is="Component"
                            :key="route.fullPath"
                            :class="
                                isPlayground ? 'h-full min-h-0' : 'flex-1'
                            "
                        />
                    </KeepAlive>
                </Transition>
            </RouterView>
        </main>
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
