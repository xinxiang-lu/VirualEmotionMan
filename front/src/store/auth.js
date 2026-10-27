import { defineStore } from 'pinia';
import { loginAdmin, loginUser, registerUser } from '@/api/auth';
import { clearAuth, saveAuth } from '@/utils/authStorage';

export const useAuthStore = defineStore('auth', {
  state: () => ({
    accessToken: '',
    user: null,
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.accessToken && state.user),
    isAdmin: (state) => state.user?.role === 'admin',
    displayName: (state) => state.user?.nickname || state.user?.phone || '访客',
  },
  actions: {
    async login(payload) {
      const data = await loginUser(payload);
      this.accessToken = data.access_token;
      this.user = data.user;
      saveAuth({
        accessToken: this.accessToken,
        user: this.user,
      });
      return data;
    },
    async loginAsAdmin(payload) {
      const data = await loginAdmin(payload);
      this.accessToken = data.access_token;
      this.user = data.user;
      saveAuth({
        accessToken: this.accessToken,
        user: this.user,
      });
      return data;
    },
    async register(payload) {
      const data = await registerUser(payload);
      this.accessToken = data.access_token;
      this.user = data.user;
      saveAuth({
        accessToken: this.accessToken,
        user: this.user,
      });
      return data;
    },
    updateUserSnapshot(payload = {}) {
      this.user = {
        ...(this.user || {}),
        ...payload,
      };
      saveAuth({
        accessToken: this.accessToken,
        user: this.user,
      });
    },
    logout() {
      this.accessToken = '';
      this.user = null;
      clearAuth();
    },
  },
});
