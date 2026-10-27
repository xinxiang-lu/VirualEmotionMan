import { apiRequest } from '@/api/http';

export const fetchAssessmentDashboard = () => apiRequest('/api/assessment/dashboard');

export const generateAssessmentDashboard = (payload = {}) =>
  apiRequest('/api/assessment/generate', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
