<template>
  <section class="page-shell">
    <div class="page-header card-surface">
      <div class="header-copy">
        <h1>人员管理</h1>
        <p>在这里查看风险分层、人工介入请求和每位用户的结构化分析结果。</p>
      </div>

      <div class="toolbar-row">
        <div class="search-box">
          <input v-model="searchKeyword" class="search-input" placeholder="按姓名或手机号即时筛选" />
          <button
            v-if="searchKeyword"
            class="clear-search-button"
            type="button"
            @click="searchKeyword = ''"
          >
            清空
          </button>
        </div>

        <select v-model="sortBy" class="sort-select">
          <option value="risk">按风险程度排序</option>
          <option value="age">按年龄排序</option>
          <option value="active">按最近活跃时间排序</option>
        </select>
      </div>

      <div v-if="hasActiveFilters" class="filter-summary">
        <span>{{ activeFilterText }}</span>
        <button class="ghost-button clear-filter-button" type="button" @click="resetFilters">清空筛选</button>
      </div>

      <div class="stats-row">
        <div class="stat-chip">
          <span>用户总数</span>
          <strong>{{ users.length }}</strong>
        </div>
        <div class="stat-chip">
          <span>当前结果</span>
          <strong>{{ filteredUsers.length }}</strong>
        </div>
        <div class="stat-chip">
          <span>待人工介入</span>
          <strong>{{ interventionRequestCount }}</strong>
        </div>
        <div class="stat-chip">
          <span>中高风险</span>
          <strong>{{ mediumHighRiskCount }}</strong>
        </div>
      </div>

      <RiskTagFilter :tags="availableTags" :selected-tags="selectedTags" @toggle="toggleTag" />
    </div>

    <div class="page-content card-surface">
      <div class="content-top">
        <div>
          <h2>用户列表</h2>
          <p>{{ listDescription }}</p>
        </div>
      </div>

      <div v-if="filteredUsers.length" class="user-list">
        <UserListCard
          v-for="user in filteredUsers"
          :key="user.id"
          :user="user"
          :refreshing="isRefreshingUser(user.id)"
          @select="selectUser"
          @intervene="handleIntervene"
          @refresh-risk="handleRefreshRisk"
        />
      </div>

      <div v-else class="empty-state">
        <strong>当前没有匹配的用户</strong>
        <p>{{ emptyStateText }}</p>
        <button v-if="hasActiveFilters" class="ghost-button empty-action" type="button" @click="resetFilters">
          清空筛选条件
        </button>
      </div>
    </div>

    <UserActionDrawer
      :visible="Boolean(selectedUser)"
      :user="selectedUser"
      :report-markdown="selectedReportMarkdown"
      :report-loading="Boolean(isReportLoading)"
      :report-error="selectedReportError"
      :report-generated-at="selectedReportGeneratedAt"
      :questionnaire-scales="questionnaireScales"
      :profile-memory-loading="Boolean(isProfileMemoryLoading)"
      @close="selectedUser = null"
      @edit-prompt="openPromptEditor"
      @intervene="handleIntervene"
      @refresh-report="handleRefreshReport"
      @start-questionnaire="handleStartQuestionnaire"
      @refresh-profile-memory="handleRefreshProfileMemory"
    />

    <PromptEditModal
      :visible="showPromptEditor"
      :prompt="editingPrompt"
      :user-name="selectedUser?.name || ''"
      @close="showPromptEditor = false"
      @save="savePrompt"
    />
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import {
  createIntervention,
  fetchAdminUsers,
  fetchAdminQuestionnaireScales,
  generateAdminUserProfileReport,
  refreshAdminUserProfileMemory,
  refreshAdminUserRiskAssessment,
  startAdminUserQuestionnaire,
  updateAdminUserPrompt,
} from '@/api/admin';
import PromptEditModal from '@/components/PromptEditModal.vue';
import RiskTagFilter from '@/components/RiskTagFilter.vue';
import UserActionDrawer from '@/components/UserActionDrawer.vue';
import UserListCard from '@/components/UserListCard.vue';
import { getRealtimeSocket } from '@/services/realtime';

const router = useRouter();
const searchKeyword = ref('');
const selectedTags = ref([]);
const sortBy = ref('risk');
const selectedUser = ref(null);
const showPromptEditor = ref(false);
const editingPrompt = ref('');
const users = ref([]);
const questionnaireScales = ref([]);
const availableTags = ref([]);
const refreshingUserIds = ref([]);
const reportCache = ref({});
const reportErrors = ref({});
const reportLoadingUserId = ref(null);
const profileMemoryLoadingUserId = ref(null);
let realtimeSocket = null;
let reloadTimer = null;

const filteredUsers = computed(() => {
  const keyword = searchKeyword.value.trim();
  let result = [...users.value];

  if (keyword) {
    result = result.filter((user) => `${user.name} ${user.account}`.includes(keyword));
  }

  if (selectedTags.value.length) {
    result = result.filter((user) => selectedTags.value.every((tag) => user.tags.includes(tag)));
  }

  if (sortBy.value === 'risk') {
    result.sort((a, b) => (b.riskWeight || 0) - (a.riskWeight || 0));
  } else if (sortBy.value === 'age') {
    result.sort((a, b) => (a.age || 0) - (b.age || 0));
  } else {
    result.sort((a, b) => b.activeAt.localeCompare(a.activeAt));
  }

  return result;
});

const interventionRequestCount = computed(
  () => users.value.filter((user) => user.transferRequested || user.hasActiveIntervention).length,
);
const mediumHighRiskCount = computed(() => users.value.filter((user) => (user.riskWeight || 0) >= 2).length);
const hasActiveFilters = computed(() => Boolean(searchKeyword.value.trim()) || selectedTags.value.length > 0);
const activeFilterText = computed(() => {
  const parts = [];
  if (searchKeyword.value.trim()) {
    parts.push(`搜索：${searchKeyword.value.trim()}`);
  }
  if (selectedTags.value.length) {
    parts.push(`标签：${selectedTags.value.join('、')}`);
  }
  return parts.join('；');
});
const listDescription = computed(() => {
  if (filteredUsers.value.length === users.value.length) {
    return '当前展示全部用户，可直接按风险、年龄或活跃度继续筛选。';
  }
  return `当前筛出 ${filteredUsers.value.length} 位用户，共 ${users.value.length} 位。`;
});
const emptyStateText = computed(() => {
  if (hasActiveFilters.value) {
    return `${activeFilterText.value} 下没有匹配结果，可以清空筛选后再试。`;
  }
  return '当前暂时没有可展示的用户记录。';
});

const resetFilters = () => {
  searchKeyword.value = '';
  selectedTags.value = [];
};

const toggleTag = (tag) => {
  if (selectedTags.value.includes(tag)) {
    selectedTags.value = selectedTags.value.filter((item) => item !== tag);
  } else {
    selectedTags.value = [...selectedTags.value, tag];
  }
};

const selectUser = async (user) => {
  selectedUser.value = user;
  try {
    await loadUsers();
  } catch (error) {
    // 保留已点击的用户卡片，避免一次刷新失败导致抽屉打不开。
  }
  const freshUser = users.value.find((item) => item.id === user.id) || user;
  selectedUser.value = freshUser;
  void loadUserProfileReport(freshUser);
};

const isRefreshingUser = (userId) => refreshingUserIds.value.includes(userId);
const formatDateTime = (value) => {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
};
const isReportLoading = computed(() => selectedUser.value && reportLoadingUserId.value === selectedUser.value.id);
const selectedReportMarkdown = computed(() => {
  if (!selectedUser.value) return '';
  return reportCache.value[selectedUser.value.id]?.markdown || '';
});
const selectedReportGeneratedAt = computed(() => {
  if (!selectedUser.value) return '';
  return formatDateTime(reportCache.value[selectedUser.value.id]?.generatedAt || '');
});
const selectedReportError = computed(() => {
  if (!selectedUser.value) return '';
  return reportErrors.value[selectedUser.value.id] || '';
});
const isProfileMemoryLoading = computed(
  () => selectedUser.value && profileMemoryLoadingUserId.value === selectedUser.value.id,
);

const loadUsers = async () => {
  const data = await fetchAdminUsers();
  users.value = data.users || [];
  availableTags.value = data.available_tags || [];

  if (selectedUser.value) {
    selectedUser.value = users.value.find((item) => item.id === selectedUser.value.id) || null;
  }
};

const scheduleUsersReload = () => {
  if (reloadTimer) window.clearTimeout(reloadTimer);
  reloadTimer = window.setTimeout(() => {
    reloadTimer = null;
    void loadUsers();
  }, 180);
};

const setupRealtime = () => {
  realtimeSocket = getRealtimeSocket();
  if (!realtimeSocket) return;
  ['intervention:requested', 'intervention:started', 'intervention:ended', 'questionnaire:updated'].forEach((eventName) => {
    realtimeSocket.off(eventName);
    realtimeSocket.on(eventName, scheduleUsersReload);
  });
};

const loadQuestionnaireScales = async () => {
  const data = await fetchAdminQuestionnaireScales();
  questionnaireScales.value = data.scales || [];
};

const loadUserProfileReport = async (user, options = {}) => {
  if (!user) return;
  const force = Boolean(options.force);

  if (!force && reportCache.value[user.id]?.markdown) {
    reportErrors.value = { ...reportErrors.value, [user.id]: '' };
    return;
  }

  reportLoadingUserId.value = user.id;
  reportErrors.value = { ...reportErrors.value, [user.id]: '' };
  try {
    const data = await generateAdminUserProfileReport(user.id);
    reportCache.value = {
      ...reportCache.value,
      [user.id]: {
        markdown: data.report_markdown || '',
        generatedAt: data.generated_at || '',
      },
    };
  } catch (error) {
    reportErrors.value = {
      ...reportErrors.value,
      [user.id]: error?.message || '心理档案报告生成失败，请稍后再试。',
    };
  } finally {
    if (reportLoadingUserId.value === user.id) {
      reportLoadingUserId.value = null;
    }
  }
};

const openPromptEditor = (user) => {
  selectedUser.value = user;
  editingPrompt.value = user.prompt;
  showPromptEditor.value = true;
};

const savePrompt = async (value) => {
  if (!selectedUser.value) return;

  try {
    const data = await updateAdminUserPrompt(selectedUser.value.id, value);
    const updatedUser = data.user;
    users.value = users.value.map((item) => (item.id === updatedUser.id ? updatedUser : item));
    selectedUser.value = updatedUser;
    editingPrompt.value = value;
    showPromptEditor.value = false;
  } catch (error) {
    window.alert(error?.message || '提示词保存失败，请稍后再试。');
  }
};

const handleIntervene = async (user) => {
  try {
    if (!user?.hasActiveIntervention) {
      await createIntervention({ user_id: user.id });
    }
    router.push({ name: 'admin-intervention', params: { userId: user.id } });
  } catch (error) {
    window.alert(error?.message || '人工介入创建失败，请稍后再试。');
  }
};

const handleRefreshRisk = async (user) => {
  if (isRefreshingUser(user.id)) return;

  refreshingUserIds.value = [...refreshingUserIds.value, user.id];
  try {
    const data = await refreshAdminUserRiskAssessment(user.id);
    const nextReportCache = { ...reportCache.value };
    const nextReportErrors = { ...reportErrors.value };
    delete nextReportCache[user.id];
    delete nextReportErrors[user.id];
    reportCache.value = nextReportCache;
    reportErrors.value = nextReportErrors;
    await loadUsers();
    window.alert(data?.message || `${user.name} 的风险评估已刷新`);
  } catch (error) {
    window.alert(error?.message || '风险评估刷新失败，请稍后再试。');
  } finally {
    refreshingUserIds.value = refreshingUserIds.value.filter((item) => item !== user.id);
  }
};

const handleRefreshReport = async (user) => {
  await loadUserProfileReport(user, { force: true });
};

const handleRefreshProfileMemory = async (user) => {
  if (!user || profileMemoryLoadingUserId.value) return;
  profileMemoryLoadingUserId.value = user.id;
  try {
    const data = await refreshAdminUserProfileMemory(user.id, { dialogueLimit: 40 });
    const updatedUser = data.user;
    users.value = users.value.map((item) => (item.id === updatedUser.id ? updatedUser : item));
    selectedUser.value = updatedUser;
    window.alert(data?.message || '用户画像已刷新');
  } catch (error) {
    window.alert(error?.message || '用户画像刷新失败，请稍后再试。');
  } finally {
    profileMemoryLoadingUserId.value = null;
  }
};

const handleStartQuestionnaire = async (user, scale) => {
  if (!user || !scale) return;
  const rawScaleId = scale.id || scale.scaleId || scale.name || scale.label || '';
  const scaleText = String(rawScaleId).toUpperCase();
  let scaleId = rawScaleId;
  if (scaleText.includes('PHQ')) scaleId = 'PHQ9';
  else if (scaleText.includes('GAD')) scaleId = 'GAD7';
  else if (scaleText.includes('ISI')) scaleId = 'ISI';

  try {
    const data = await startAdminUserQuestionnaire(user.id, { scaleId });
    await loadUsers();
    window.alert(data?.message || `${scale.name || '量表'} 已发起，请用户在聊天中继续回答。`);
  } catch (error) {
    window.alert(error?.message || '量表发起失败，请稍后再试。');
  }
};

onMounted(async () => {
  try {
    setupRealtime();
    await Promise.all([loadUsers(), loadQuestionnaireScales()]);
  } catch (error) {
    window.alert(error?.message || '人员列表加载失败，请稍后再试。');
  }
});

onBeforeUnmount(() => {
  if (reloadTimer) {
    window.clearTimeout(reloadTimer);
    reloadTimer = null;
  }
  if (realtimeSocket) {
    ['intervention:requested', 'intervention:started', 'intervention:ended', 'questionnaire:updated'].forEach((eventName) => {
      realtimeSocket.off(eventName);
    });
  }
});
</script>

<style scoped>
.page-shell {
  display: grid;
  gap: 16px;
  min-height: 0;
}

.page-header,
.page-content {
  padding: 22px;
}

.page-header {
  display: grid;
  gap: 16px;
  position: relative;
  overflow: hidden;
}

.page-header::after {
  content: "";
  position: absolute;
  right: -70px;
  top: -110px;
  width: 260px;
  height: 260px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(141, 180, 217, 0.22), transparent 68%);
  pointer-events: none;
}

.header-copy {
  display: grid;
  gap: 8px;
}

.header-copy h1,
.content-top h2 {
  margin: 0;
  color: var(--text-main);
}

.header-copy p,
.content-top p {
  margin: 0;
  color: var(--text-soft);
  line-height: 1.7;
}

.toolbar-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
}

.search-box {
  position: relative;
}

.search-input,
.sort-select {
  border: 1px solid var(--line-soft);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.84);
  padding: 0.9rem 1rem;
  color: var(--text-main);
  outline: none;
  box-shadow: 0 8px 18px rgba(75,111,116,.05);
}

.search-input {
  width: 100%;
  padding-right: 4.8rem;
}

.clear-search-button {
  position: absolute;
  top: 50%;
  right: 0.9rem;
  transform: translateY(-50%);
  border: none;
  background: transparent;
  color: var(--text-soft);
  font-size: 0.8rem;
}

.filter-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0.9rem 1rem;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.72);
  color: var(--text-soft);
  line-height: 1.7;
}

.clear-filter-button,
.empty-action {
  white-space: nowrap;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.stat-chip {
  border-radius: 20px;
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.78), rgba(245, 250, 248, 0.72));
  border: 1px solid rgba(90,117,118,.08);
  padding: 15px 16px;
  display: grid;
  gap: 6px;
  box-shadow: 0 10px 24px rgba(75,111,116,.06);
}

.stat-chip span {
  color: var(--text-soft);
  font-size: 0.82rem;
}

.stat-chip strong {
  color: var(--text-main);
  font-size: 1.15rem;
}

.page-content {
  display: grid;
  gap: 16px;
  min-height: 0;
  background:
    linear-gradient(180deg, rgba(255,255,255,.78), rgba(249,252,250,.7)),
    radial-gradient(circle at 100% 0%, rgba(141,180,217,.12), transparent 34%);
}

.content-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.user-list {
  display: grid;
  gap: 12px;
  max-height: min(70vh, 980px);
  overflow: auto;
  padding: 2px 6px 2px 2px;
  scrollbar-width: thin;
}

.empty-state {
  min-height: 220px;
  border-radius: 24px;
  background:
    radial-gradient(circle at top, rgba(255, 255, 255, 0.9), transparent 38%),
    linear-gradient(180deg, rgba(221, 234, 245, 0.72), rgba(241, 246, 242, 0.7));
  display: grid;
  place-items: center;
  text-align: center;
  padding: 24px;
}

.empty-state strong {
  color: var(--text-main);
  font-size: 1.02rem;
}

.empty-state p {
  margin: 8px 0 0;
  color: var(--text-soft);
  line-height: 1.7;
}

.empty-action {
  margin-top: 14px;
}

@media (max-width: 1024px) {
  .stats-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .toolbar-row,
  .stats-row,
  .content-top,
  .filter-summary {
    grid-template-columns: 1fr;
    display: grid;
  }
}
</style>
