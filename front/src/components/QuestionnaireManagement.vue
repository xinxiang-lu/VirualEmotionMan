<template>
  <section class="questionnaire-page">
    <div class="page-header card-surface">
      <div>
        <h1>问卷管理</h1>
        <p>维护对话式心理量表库。题目、选项、关键词和风险阈值在这里统一查看与配置。</p>
      </div>
      <div class="header-actions">
        <label class="ghost-button upload-button">
          上传 JSON
          <input type="file" accept="application/json,.json" @change="handleJsonUpload" />
        </label>
        <button class="primary-button" type="button" @click="startCreate">新增问卷</button>
      </div>
    </div>

    <div class="questionnaire-layout">
      <aside class="scale-list card-surface">
        <button
          v-for="scale in scales"
          :key="scale.id"
          :class="['scale-list-item', selectedScale?.id === scale.id ? 'is-active' : '']"
          type="button"
          @click="selectScale(scale)"
        >
          <span class="scale-id">{{ scale.id }}</span>
          <strong>{{ scale.name }}</strong>
          <span>{{ scale.label }}</span>
          <small>{{ scale.itemCount || scale.items?.length || 0 }} 题 · {{ scale.scoreRange }}</small>
        </button>
        <p v-if="!scales.length" class="empty-text">暂无问卷配置。</p>
      </aside>

      <section class="scale-detail card-surface">
        <div v-if="selectedScale && !editing" class="detail-view">
          <div class="detail-title">
            <div>
              <h2>{{ selectedScale.name }}</h2>
              <p>{{ selectedScale.label }} · {{ selectedScale.timeWindow || '最近两周' }}</p>
            </div>
            <div class="detail-actions">
              <button class="ghost-button" type="button" @click="startEdit(selectedScale)">编辑</button>
              <button class="ghost-button danger-text" type="button" @click="deleteScale(selectedScale)">删除</button>
            </div>
          </div>

          <p class="description">{{ selectedScale.description || '暂无描述。' }}</p>

          <div class="severity-row">
            <span v-for="item in selectedScale.severity || []" :key="`${item.level}-${item.min}`">
              {{ riskLabel(item.level) }}：{{ item.min }}-{{ item.max }} 分
            </span>
          </div>

          <div class="item-list">
            <article v-for="(item, index) in selectedScale.items || []" :key="item.code" class="question-item">
              <div class="question-title">
                <strong>{{ index + 1 }}. {{ item.construct }}</strong>
                <span>{{ item.dimensionLabel || item.dimension }} · 最高 {{ item.maxScore }} 分</span>
              </div>
              <p>{{ item.prompt }}</p>
              <div class="option-row">
                <b v-for="option in item.options || []" :key="`${item.code}-${option.score}`">
                  {{ option.score }}={{ option.label }}
                </b>
              </div>
              <small v-if="item.keywords?.length">关键词：{{ item.keywords.join('、') }}</small>
            </article>
          </div>
        </div>

        <form v-else class="edit-form" @submit.prevent="saveScale">
          <div class="detail-title">
            <div>
              <h2>{{ formMode === 'create' ? '新增问卷' : '编辑问卷' }}</h2>
              <p>按题目逐条填写。系统会把这些题项转化为自然对话，并在完整回答后进入正式评分。</p>
            </div>
            <button class="ghost-button" type="button" @click="cancelEdit">取消</button>
          </div>

          <div class="form-card">
            <h3>基础信息</h3>
            <div class="form-grid">
              <label>
                <span>问卷 ID</span>
                <input v-model.trim="form.id" :disabled="formMode === 'edit'" placeholder="PHQ9" />
              </label>
              <label>
                <span>问卷名称</span>
                <input v-model.trim="form.name" placeholder="PHQ-9" />
              </label>
              <label>
                <span>中文说明</span>
                <input v-model.trim="form.label" placeholder="抑郁相关症状筛查" />
              </label>
              <label>
                <span>时间范围</span>
                <input v-model.trim="form.timeWindow" placeholder="最近两周" />
              </label>
            </div>

            <label>
              <span>用途描述</span>
              <textarea v-model.trim="form.description" rows="3" placeholder="说明该问卷适用场景、筛查目标和注意事项。"></textarea>
            </label>
          </div>

          <div class="form-card">
            <div class="section-title-row">
              <div>
                <h3>题目设置</h3>
                <p>每道题可独立设置维度、测量点、自然问题、分值和关键词。</p>
              </div>
              <button class="ghost-button" type="button" @click="addItem">新增题目</button>
            </div>

            <article v-for="(item, index) in form.items" :key="item.localId" class="item-editor">
              <div class="item-editor-header">
                <strong>第 {{ index + 1 }} 题</strong>
                <div class="mini-actions">
                  <button type="button" @click="moveItem(index, -1)" :disabled="index === 0">上移</button>
                  <button type="button" @click="moveItem(index, 1)" :disabled="index === form.items.length - 1">下移</button>
                  <button type="button" class="danger-text" @click="removeItem(index)">删除</button>
                </div>
              </div>

              <div class="form-grid item-grid">
                <label>
                  <span>维度</span>
                  <input v-model.trim="item.dimension" placeholder="睡眠状态" />
                </label>
                <label>
                  <span>测量点</span>
                  <input v-model.trim="item.construct" placeholder="入睡困难 / 兴趣下降" />
                </label>
                <label>
                  <span>最高分</span>
                  <select v-model.number="item.maxScore">
                    <option :value="1">1 分</option>
                    <option :value="2">2 分</option>
                    <option :value="3">3 分</option>
                    <option :value="4">4 分</option>
                  </select>
                </label>
                <label>
                  <span>关键词</span>
                  <input v-model.trim="item.keywordsText" placeholder="睡不着,失眠,两三点" />
                </label>
              </div>

              <label>
                <span>自然对话问题</span>
                <textarea v-model.trim="item.prompt" rows="2" placeholder="例如：最近两周，你晚上入睡或者睡眠维持会不会比较困难？"></textarea>
              </label>

              <div class="option-row option-row--preview">
                <b v-for="option in scoreOptions(item.maxScore)" :key="`${item.localId}-${option.score}`">
                  {{ option.score }}={{ option.label }}
                </b>
              </div>
            </article>

            <div v-if="!form.items.length" class="empty-editor">
              <strong>还没有题目</strong>
              <p>至少添加一道题后才能保存问卷。</p>
              <button class="ghost-button" type="button" @click="addItem">添加第一题</button>
            </div>
          </div>

          <div class="form-actions">
            <span>{{ form.items.length }} 道题 · 最高总分 {{ totalMaxScore }}</span>
            <button class="primary-button" type="submit">保存问卷</button>
          </div>
        </form>
      </section>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import {
  createAdminQuestionnaireScale,
  deleteAdminQuestionnaireScale,
  fetchAdminQuestionnaireScales,
  updateAdminQuestionnaireScale,
} from '@/api/admin';

const scales = ref([]);
const selectedScale = ref(null);
const editing = ref(false);
const formMode = ref('create');
const form = reactive({
  id: '',
  name: '',
  label: '',
  timeWindow: '最近两周',
  description: '',
  items: [],
});

const newLocalId = () => `${Date.now()}-${Math.random().toString(16).slice(2)}`;

const scoreOptions = (maxScore = 3) => {
  const labels = Number(maxScore) >= 4
    ? ['无', '轻度', '中度', '重度', '非常严重']
    : ['没有', '偶尔/几天', '经常/一半以上时间', '几乎每天/非常明显'];
  return Array.from({ length: Number(maxScore || 3) + 1 }, (_, score) => ({
    score,
    label: labels[Math.min(score, labels.length - 1)],
  }));
};

const totalMaxScore = computed(() =>
  form.items.reduce((total, item) => total + Number(item.maxScore || 0), 0),
);

const riskLabel = (level) => ({ low: '低', medium: '中', high: '高', critical: '高' }[level] || level);

const normalizeEditItem = (item = {}, index = 0) => ({
  localId: newLocalId(),
  code: item.code || `${form.id.toLowerCase()}_${String(index + 1).padStart(2, '0')}`,
  dimension: item.dimensionLabel || item.dimension || '',
  construct: item.construct || '',
  prompt: item.prompt || '',
  maxScore: Number(item.maxScore || item.max_score || 3),
  keywordsText: Array.isArray(item.keywords) ? item.keywords.join(',') : (item.keywords || ''),
});

const buildPayloadItems = () =>
  form.items.map((item, index) => ({
    code: item.code || `${form.id.toLowerCase()}_${String(index + 1).padStart(2, '0')}`,
    dimension: item.dimension || 'custom',
    construct: item.construct || item.prompt.slice(0, 24),
    prompt: item.prompt,
    maxScore: Number(item.maxScore || 3),
    keywords: item.keywordsText
      .split(/[,，、]/)
      .map((value) => value.trim())
      .filter(Boolean),
  }));

const loadScales = async () => {
  const data = await fetchAdminQuestionnaireScales();
  scales.value = data.scales || [];
  if (!selectedScale.value && scales.value.length) {
    selectedScale.value = scales.value[0];
  } else if (selectedScale.value) {
    selectedScale.value = scales.value.find((item) => item.id === selectedScale.value.id) || scales.value[0] || null;
  }
};

const fillForm = (scale = {}) => {
  form.id = scale.id || '';
  form.name = scale.name || '';
  form.label = scale.label || '';
  form.timeWindow = scale.timeWindow || '最近两周';
  form.description = scale.description || '';
  form.items = (scale.items || []).map((item, index) => normalizeEditItem(item, index));
};

const selectScale = (scale) => {
  selectedScale.value = scale;
  editing.value = false;
};

const startCreate = () => {
  formMode.value = 'create';
  fillForm({});
  addItem();
  editing.value = true;
};

const startEdit = (scale) => {
  formMode.value = 'edit';
  fillForm(scale);
  editing.value = true;
};

const cancelEdit = () => {
  editing.value = false;
  if (!selectedScale.value && scales.value.length) selectedScale.value = scales.value[0];
};

const addItem = () => {
  form.items.push(
    normalizeEditItem(
      {
        dimension: '',
        construct: '',
        prompt: '',
        maxScore: 3,
        keywords: [],
      },
      form.items.length,
    ),
  );
};

const removeItem = (index) => {
  form.items.splice(index, 1);
};

const moveItem = (index, direction) => {
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= form.items.length) return;
  const [item] = form.items.splice(index, 1);
  form.items.splice(nextIndex, 0, item);
};

const validateForm = () => {
  if (!form.id.trim()) return '问卷 ID 不能为空。';
  if (!form.name.trim()) return '问卷名称不能为空。';
  if (!form.items.length) return '至少需要添加一道题。';
  const invalidIndex = form.items.findIndex((item) => !item.prompt.trim());
  if (invalidIndex >= 0) return `第 ${invalidIndex + 1} 题的问题不能为空。`;
  return '';
};

const saveScale = async () => {
  const invalidMessage = validateForm();
  if (invalidMessage) {
    window.alert(invalidMessage);
    return;
  }

  const payload = {
    id: form.id,
    name: form.name,
    label: form.label,
    timeWindow: form.timeWindow,
    description: form.description,
    items: buildPayloadItems(),
  };
  try {
    if (formMode.value === 'edit') {
      await updateAdminQuestionnaireScale(form.id, payload);
    } else {
      await createAdminQuestionnaireScale(payload);
    }
    await loadScales();
    selectedScale.value = scales.value.find((item) => item.id === payload.id) || selectedScale.value;
    editing.value = false;
    window.alert('问卷配置已保存。');
  } catch (error) {
    window.alert(error?.message || '保存失败，请检查问卷 ID 和题项格式。');
  }
};

const deleteScale = async (scale) => {
  if (!scale?.id) return;
  if (!window.confirm(`确定删除问卷“${scale.name}”吗？`)) return;
  try {
    await deleteAdminQuestionnaireScale(scale.id);
    selectedScale.value = null;
    await loadScales();
    window.alert('问卷已删除。');
  } catch (error) {
    window.alert(error?.message || '删除失败。');
  }
};

const handleJsonUpload = async (event) => {
  const file = event.target.files?.[0];
  event.target.value = '';
  if (!file) return;
  try {
    const text = await file.text();
    const payload = JSON.parse(text);
    const imported = Array.isArray(payload.scales) ? payload.scales : [payload];
    const existingIds = new Set(scales.value.map((scale) => scale.id));
    for (const scale of imported) {
      if (existingIds.has(scale.id)) {
        await updateAdminQuestionnaireScale(scale.id, scale);
      } else {
        await createAdminQuestionnaireScale(scale);
      }
    }
    await loadScales();
    window.alert(`已导入 ${imported.length} 个问卷。`);
  } catch (error) {
    window.alert(error?.message || 'JSON 导入失败，请检查格式。');
  }
};

onMounted(async () => {
  try {
    await loadScales();
  } catch (error) {
    window.alert(error?.message || '问卷列表加载失败。');
  }
});
</script>

<style scoped>
.questionnaire-page { display:grid; gap:18px; }
.page-header {
  padding:24px;
  display:flex;
  justify-content:space-between;
  gap:18px;
  align-items:center;
  overflow:hidden;
  position:relative;
}
.page-header::after {
  content:"";
  position:absolute;
  right:-80px;
  top:-100px;
  width:240px;
  height:240px;
  border-radius:50%;
  background:radial-gradient(circle, rgba(141,180,217,.26), transparent 68%);
  pointer-events:none;
}
.page-header h1, .detail-title h2 { margin:0; color:var(--text-main); }
.page-header p, .detail-title p, .description, .empty-text, .section-title-row p { color:var(--text-soft); line-height:1.7; }
.header-actions, .detail-actions, .form-actions { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
.upload-button { position:relative; overflow:hidden; }
.upload-button input { position:absolute; inset:0; opacity:0; cursor:pointer; }
.questionnaire-layout { display:grid; grid-template-columns:minmax(240px, 1.15fr) minmax(0, 3.85fr); gap:18px; align-items:start; }
.scale-list, .scale-detail { padding:20px; }
.scale-list {
  display:grid;
  gap:10px;
  align-content:start;
  position:sticky;
  top:18px;
  max-height:calc(100vh - 170px);
  overflow:auto;
}
.scale-list-item {
  border:1px solid rgba(90,117,118,.14);
  border-radius:16px;
  background:rgba(255,255,255,.74);
  padding:15px;
  display:grid;
  gap:6px;
  text-align:left;
  cursor:pointer;
  transition:.18s ease;
  box-shadow:0 8px 20px rgba(75,111,116,.06);
}
.scale-list-item:hover { transform:translateY(-1px); border-color:rgba(43,125,116,.26); }
.scale-list-item.is-active { border-color:rgba(43,125,116,.42); background:rgba(43,125,116,.08); box-shadow:0 10px 26px rgba(75,111,116,.12); }
.scale-id {
  width:max-content;
  border-radius:999px;
  padding:3px 8px;
  background:rgba(43,125,116,.1);
  color:var(--brand-deep);
  font-size:.74rem;
  font-weight:800;
  letter-spacing:.04em;
}
.scale-list-item strong, .question-title strong, .form-card h3, .item-editor-header strong { color:var(--text-main); }
.scale-list-item span, .scale-list-item small, .question-title span { color:var(--text-soft); }
.detail-view, .edit-form { display:grid; gap:16px; }
.detail-title {
  display:flex;
  align-items:start;
  justify-content:space-between;
  gap:14px;
  padding-bottom:14px;
  border-bottom:1px solid rgba(90,117,118,.1);
}
.danger-text { color:#b43a2c; }
.severity-row, .option-row { display:flex; flex-wrap:wrap; gap:8px; }
.severity-row span, .option-row b { border-radius:999px; padding:5px 10px; background:rgba(80,93,96,.08); color:var(--text-soft); font-size:.82rem; }
.item-list { display:grid; gap:12px; }
.question-item, .item-editor, .form-card {
  border:1px solid rgba(90,117,118,.12);
  border-radius:18px;
  padding:16px;
  background:rgba(255,255,255,.74);
  box-shadow:0 10px 24px rgba(75,111,116,.06);
}
.question-title, .item-editor-header, .section-title-row { display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; align-items:flex-start; }
.section-title-row h3, .section-title-row p, .form-card h3 { margin:0; }
.question-item p { margin:8px 0; color:var(--text-main); line-height:1.65; }
.question-item small { color:var(--text-soft); }
.form-grid { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:12px; }
.item-grid { grid-template-columns:1.15fr 1.3fr .6fr 1.35fr; }
.edit-form label { display:grid; gap:6px; color:var(--text-soft); font-size:.9rem; }
.edit-form input, .edit-form textarea, .edit-form select { width:100%; border:1px solid rgba(90,117,118,.18); border-radius:12px; padding:11px 12px; background:rgba(255,255,255,.92); color:var(--text-main); resize:vertical; outline:none; }
.edit-form input:focus, .edit-form textarea:focus, .edit-form select:focus { border-color:rgba(43,125,116,.48); box-shadow:0 0 0 3px rgba(43,125,116,.08); }
.form-card { display:grid; gap:14px; }
.item-editor {
  display:grid;
  gap:12px;
  background:
    linear-gradient(180deg, rgba(255,255,255,.92), rgba(247,251,249,.78)),
    radial-gradient(circle at top right, rgba(141,180,217,.16), transparent 42%);
}
.mini-actions { display:flex; flex-wrap:wrap; gap:6px; }
.mini-actions button { border:1px solid rgba(90,117,118,.16); border-radius:999px; padding:4px 9px; background:#fff; color:var(--text-soft); cursor:pointer; }
.mini-actions button:disabled { opacity:.45; cursor:not-allowed; }
.option-row--preview { margin-top:-2px; }
.empty-editor { border:1px dashed rgba(43,125,116,.26); border-radius:16px; padding:18px; text-align:center; background:rgba(255,255,255,.58); color:var(--text-soft); }
.empty-editor strong { color:var(--text-main); }
.form-actions {
  justify-content:space-between;
  padding:14px;
  color:var(--text-soft);
  border-radius:16px;
  background:rgba(255,255,255,.62);
  border:1px solid rgba(90,117,118,.1);
  position:sticky;
  bottom:12px;
  backdrop-filter:blur(10px);
}
@media (max-width: 1024px) {
  .questionnaire-layout, .form-grid, .item-grid { grid-template-columns:1fr; }
  .scale-list { position:static; max-height:none; }
  .page-header, .detail-title, .form-actions { align-items:stretch; flex-direction:column; }
}
</style>
