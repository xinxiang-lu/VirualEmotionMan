<template>
  <section class="assessment-summary card-surface">
    <div class="summary-header">
      <div class="summary-headline">
        <h1>近期状态评估</h1>
        <span class="time-chip">{{ summary.updatedAt }}</span>
      </div>
      <p>{{ summary.mood }}</p>
    </div>
    <div class="summary-grid">
      <article v-for="item in cards" :key="item.title" class="summary-card">
        <span>{{ item.title }}</span>
        <strong>{{ item.value }}</strong>
        <p>{{ item.description }}</p>
      </article>
    </div>
    <div class="summary-footer">
      <strong>简要建议</strong>
      <p>{{ summary.advice }}</p>
    </div>
  </section>
</template>

<script setup>
defineProps({ summary: { type: Object, default: () => ({}) }, cards: { type: Array, default: () => [] } });
</script>

<style scoped>
.assessment-summary { padding:24px; display:grid; gap:22px; }
.summary-header { display:grid; gap:10px; }
.summary-headline { display:flex; align-items:center; justify-content:space-between; gap:16px; }
.summary-header h1 { margin:0; color:var(--text-main); }
.summary-header p { margin:0; color:var(--text-soft); }
.time-chip { border-radius:999px; padding:.58rem .9rem; background:rgba(227,238,247,.82); color:var(--brand-deep); font-size:.88rem; }
.summary-grid { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:16px; }
.summary-card { border-radius:22px; padding:18px; background:rgba(255,255,255,.72); }
.summary-card span, .summary-card p { color:var(--text-soft); }
.summary-card strong { display:block; margin-top:10px; color:var(--text-main); font-size:1.2rem; }
.summary-card p { margin:10px 0 0; line-height:1.7; }
.summary-footer strong { color:var(--text-main); }
.summary-footer p { margin:10px 0 0; color:var(--text-soft); line-height:1.8; }
@media (max-width:768px) { .summary-grid { grid-template-columns:1fr; } .summary-headline { align-items:flex-start; flex-direction:column; } }
</style>
