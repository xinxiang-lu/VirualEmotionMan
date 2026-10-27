const AUTH_STORAGE_KEY = 'youth-mind-auth';

let authSnapshot = {
  accessToken: '',
  user: null,
};

const clearLegacyPersistedAuth = () => {
  if (typeof window === 'undefined' || !window.localStorage) {
    return;
  }

  try {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
  } catch (error) {
    console.error('Failed to clear legacy auth storage:', error);
  }
};

clearLegacyPersistedAuth();

const cloneAuthSnapshot = () => ({
  accessToken: authSnapshot.accessToken || '',
  user: authSnapshot.user ? { ...authSnapshot.user } : null,
});

export const getStoredAuth = () => cloneAuthSnapshot();

export const getAccessToken = () => authSnapshot.accessToken || '';

export const saveAuth = ({ accessToken = '', user = null }) => {
  authSnapshot = {
    accessToken: accessToken || '',
    user: user ? { ...user } : null,
  };
};

export const clearAuth = () => {
  authSnapshot = {
    accessToken: '',
    user: null,
  };

  clearLegacyPersistedAuth();
};
