import { apiRequest } from '@/api/http';

export const loginUser = (payload) =>
  apiRequest('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const loginAdmin = (payload) =>
  apiRequest('/api/auth/admin-login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const registerUser = (payload) =>
  apiRequest('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const uploadAvatar = (file) => {
  const formData = new FormData();
  formData.append('file', file);

  return apiRequest('/api/auth/avatar-upload', {
    method: 'POST',
    body: formData,
  });
};

export const requestResetCode = (payload) =>
  apiRequest('/api/auth/forgot-password/code', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const resetPassword = (payload) =>
  apiRequest('/api/auth/forgot-password/reset', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
