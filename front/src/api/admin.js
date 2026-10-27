import { apiRequest } from '@/api/http';

export const fetchAdminUsers = (params = {}) => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, Array.isArray(value) ? value.join(',') : value);
    }
  });

  const suffix = search.toString() ? `?${search.toString()}` : '';
  return apiRequest(`/api/admin/users${suffix}`);
};

export const updateAdminUserPrompt = (userId, prompt) =>
  apiRequest(`/api/admin/users/${userId}/prompt`, {
    method: 'PATCH',
    body: JSON.stringify({ prompt }),
  });

export const refreshAdminUserRiskAssessment = (userId, payload = {}) =>
  apiRequest(`/api/admin/users/${userId}/risk-assessment/refresh`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const refreshAdminUserProfileMemory = (userId, payload = {}) =>
  apiRequest(`/api/admin/users/${userId}/profile-memory/refresh`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const startAdminUserQuestionnaire = (userId, payload = {}) =>
  apiRequest(`/api/admin/users/${userId}/questionnaire/start`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const fetchAdminQuestionnaireScales = () => apiRequest('/api/admin/questionnaire/scales');

export const createAdminQuestionnaireScale = (payload) =>
  apiRequest('/api/admin/questionnaire/scales', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const updateAdminQuestionnaireScale = (scaleId, payload) =>
  apiRequest(`/api/admin/questionnaire/scales/${encodeURIComponent(scaleId)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });

export const deleteAdminQuestionnaireScale = (scaleId) =>
  apiRequest(`/api/admin/questionnaire/scales/${encodeURIComponent(scaleId)}`, {
    method: 'DELETE',
  });

export const generateAdminUserProfileReport = (userId, payload = {}) =>
  apiRequest(`/api/admin/users/${userId}/profile-report/generate`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const fetchBusinessStats = () => apiRequest('/api/admin/business-stats');

export const fetchOpsStats = () => apiRequest('/api/admin/ops-stats');

export const fetchSystemSettings = () => apiRequest('/api/admin/system-settings');

export const updateSystemSettings = (payload) =>
  apiRequest('/api/admin/system-settings', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });

export const createIntervention = (payload) =>
  apiRequest('/api/admin/interventions', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const fetchInterventionByUser = (userId) =>
  apiRequest(`/api/admin/interventions/user/${userId}`);

export const sendInterventionMessage = (sessionId, content) =>
  apiRequest(`/api/admin/interventions/${sessionId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  });

export const finishIntervention = (sessionId) =>
  apiRequest(`/api/admin/interventions/${sessionId}/finish`, {
    method: 'POST',
  });
