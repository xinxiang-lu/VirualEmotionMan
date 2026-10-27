<template>
  <article class="markdown-report" v-html="renderedHtml"></article>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  content: { type: String, default: '' },
});

const escapeHtml = (text) =>
  text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');

const formatInline = (text) =>
  escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>');

const renderMarkdown = (markdown) => {
  const lines = (markdown || '').replace(/\r\n/g, '\n').split('\n');
  const html = [];
  const paragraph = [];
  let listType = '';

  const flushParagraph = () => {
    if (!paragraph.length) return;
    html.push(`<p>${formatInline(paragraph.join(' '))}</p>`);
    paragraph.length = 0;
  };

  const closeList = () => {
    if (!listType) return;
    html.push(listType === 'ol' ? '</ol>' : '</ul>');
    listType = '';
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      closeList();
      continue;
    }

    const headingMatch = line.match(/^(#{1,3})\s+(.*)$/);
    if (headingMatch) {
      flushParagraph();
      closeList();
      const level = headingMatch[1].length;
      html.push(`<h${level}>${formatInline(headingMatch[2])}</h${level}>`);
      continue;
    }

    const unorderedMatch = line.match(/^[-*]\s+(.*)$/);
    if (unorderedMatch) {
      flushParagraph();
      if (listType !== 'ul') {
        closeList();
        html.push('<ul>');
        listType = 'ul';
      }
      html.push(`<li>${formatInline(unorderedMatch[1])}</li>`);
      continue;
    }

    const orderedMatch = line.match(/^\d+\.\s+(.*)$/);
    if (orderedMatch) {
      flushParagraph();
      if (listType !== 'ol') {
        closeList();
        html.push('<ol>');
        listType = 'ol';
      }
      html.push(`<li>${formatInline(orderedMatch[1])}</li>`);
      continue;
    }

    closeList();
    paragraph.push(line);
  }

  flushParagraph();
  closeList();
  return html.join('');
};

const renderedHtml = computed(() => renderMarkdown(props.content));
</script>

<style scoped>
.markdown-report {
  color: var(--text-soft);
  line-height: 1.8;
}

.markdown-report :deep(h1),
.markdown-report :deep(h2),
.markdown-report :deep(h3) {
  color: var(--text-main);
  line-height: 1.35;
}

.markdown-report :deep(h1) {
  margin: 0 0 16px;
  font-size: 1.18rem;
}

.markdown-report :deep(h2) {
  margin: 20px 0 10px;
  font-size: 1rem;
}

.markdown-report :deep(h3) {
  margin: 16px 0 8px;
  font-size: 0.92rem;
}

.markdown-report :deep(p) {
  margin: 10px 0 0;
}

.markdown-report :deep(ul),
.markdown-report :deep(ol) {
  margin: 10px 0 0;
  padding-left: 1.2rem;
}

.markdown-report :deep(li + li) {
  margin-top: 6px;
}

.markdown-report :deep(code) {
  border-radius: 8px;
  padding: 0.1rem 0.36rem;
  background: rgba(225, 232, 238, 0.78);
  color: var(--text-main);
  font-family: 'Consolas', 'SFMono-Regular', monospace;
  font-size: 0.84em;
}
</style>
