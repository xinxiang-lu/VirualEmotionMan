import { apiRequest } from '@/api/http';

export const fetchConversations = () => apiRequest('/api/conversations');

export const createConversation = (payload = {}) =>
  apiRequest('/api/conversations', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const renameConversation = (conversationId, payload) =>
  apiRequest(`/api/conversations/${conversationId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });

export const deleteConversation = (conversationId) =>
  apiRequest(`/api/conversations/${conversationId}`, {
    method: 'DELETE',
  });

export const fetchConversationMessages = (conversationId) =>
  apiRequest(`/api/conversations/${conversationId}/messages`);

export const sendConversationMessage = (conversationId, payload) =>
  apiRequest(`/api/conversations/${conversationId}/messages`, {
    method: 'POST',
    body: payload instanceof FormData ? payload : JSON.stringify(payload),
  });

export const fetchQuestionnaireScales = () => apiRequest('/api/questionnaire/scales');

export const fetchQuestionnaireStatus = (conversationId) =>
  apiRequest(`/api/conversations/${conversationId}/questionnaire/status`);

export const startQuestionnaireSession = (conversationId, payload) =>
  apiRequest(`/api/conversations/${conversationId}/questionnaire/start`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const cancelQuestionnaireSession = (conversationId) =>
  apiRequest(`/api/conversations/${conversationId}/questionnaire/cancel`, {
    method: 'POST',
  });

export const fetchMessageMultimodalAnalysis = (conversationId, messageId) =>
  apiRequest(`/api/conversations/${conversationId}/messages/${messageId}/multimodal-analysis`);

export const fetchMyProfile = () => apiRequest('/api/users/me/profile');

export const updateMyProfile = (payload) =>
  apiRequest('/api/users/me/profile', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });

export const fetchMySettings = () => apiRequest('/api/users/me/settings');

export const updateMySettings = (payload) =>
  apiRequest('/api/users/me/settings', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });

export const requestHumanIntervention = (payload = {}) =>
  apiRequest('/api/interventions/request', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
