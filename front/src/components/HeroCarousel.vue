<template>
  <section class="carousel card-surface">
    <div class="copy-block" :style="{ background: currentSlide.visual }">
      <h1>{{ currentSlide.title }}</h1>
      <p class="description">{{ currentSlide.description }}</p>
    </div>

    <div class="carousel-footer">
      <div class="indicator-group">
        <button
          v-for="(slide, index) in slides"
          :key="slide.id"
          :class="['indicator', index === currentIndex ? 'is-active' : '']"
          :aria-label="`切换到第${index + 1}张`"
          type="button"
          @click="setSlide(index)"
        />
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

const props = defineProps({
  slides: {
    type: Array,
    default: () => [],
  },
  autoplayMs: {
    type: Number,
    default: 5000,
  },
});

const currentIndex = ref(0);
let timerId = null;

const currentSlide = computed(() => props.slides[currentIndex.value] || {});

const setSlide = (index) => {
  currentIndex.value = index;
  startAutoplay();
};

const startAutoplay = () => {
  if (timerId) {
    window.clearInterval(timerId);
  }

  if (props.slides.length <= 1) {
    return;
  }

  timerId = window.setInterval(() => {
    currentIndex.value = (currentIndex.value + 1) % props.slides.length;
  }, props.autoplayMs);
};

onMounted(startAutoplay);

onBeforeUnmount(() => {
  if (timerId) {
    window.clearInterval(timerId);
  }
});
</script>

<style scoped>
.carousel {
  min-height: 100%;
  height: 100%;
  padding: 20px;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
}

.copy-block {
  min-height: 0;
  height: 100%;
  border-radius: var(--radius-xl);
  padding: clamp(28px, 5vw, 56px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.45);
}

.copy-block h1 {
  max-width: 14ch;
  margin: 0;
  color: var(--text-main);
  font-size: clamp(2.2rem, 5vw, 4rem);
  line-height: 1.12;
}

.description {
  max-width: 44rem;
  margin: 24px 0 0;
  color: var(--text-soft);
  line-height: 1.9;
  font-size: 1.02rem;
}

.carousel-footer {
  margin-top: 22px;
  display: flex;
  justify-content: center;
}

.indicator-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.indicator {
  width: 12px;
  height: 12px;
  border: none;
  border-radius: 999px;
  background: rgba(113, 133, 130, 0.24);
}

.indicator.is-active {
  width: 36px;
  background: linear-gradient(90deg, var(--brand-deep), #7fb1de);
}

@media (max-width: 768px) {
  .carousel {
    padding: 16px;
  }

  .copy-block {
    min-height: 0;
  }

  .copy-block h1 {
    max-width: none;
  }
}
</style>
