<script setup lang="ts">
import type { RunState } from '../contracts';
import { states } from '../presentation';
defineProps<{ state: RunState }>();
</script>

<template>
  <span class="badge" :class="states[state].tone">{{ states[state].label }}</span>
</template>
