<template>
  <section class="home-view">
    <HeroCarousel :slides="slides" />
  </section>
</template>

<script setup>
import HeroCarousel from '@/components/HeroCarousel.vue';
import { homeSlides } from '@/mocks/homeSlides';

const slides = homeSlides;
</script>

<style scoped>
.home-view {
  display: grid;
  flex: 1;
  min-height: 100%;
}
</style>
