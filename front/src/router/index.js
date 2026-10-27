import { createRouter, createWebHistory } from 'vue-router';
import { APP_NAME } from '@/config';
import { getStoredAuth } from '@/utils/authStorage';
import AdminDashboard from '@/views/AdminDashboard.vue';
import AdminInterventionView from '@/views/AdminInterventionView.vue';
import AdminLoginView from '@/views/AdminLoginView.vue';
import AssessmentView from '@/views/AssessmentView.vue';
import ChatView from '@/views/ChatView.vue';
import ForgotPasswordView from '@/views/ForgotPasswordView.vue';
import HomeView from '@/views/HomeView.vue';
import LoginView from '@/views/LoginView.vue';
import RegisterView from '@/views/RegisterView.vue';

const routes = [
  { path: '/', name: 'home', component: HomeView, meta: { title: '首页' } },
  { path: '/login', name: 'login', component: LoginView, meta: { title: '用户登录' } },
  { path: '/admin-login', name: 'admin-login', component: AdminLoginView, meta: { title: '管理员登录' } },
  { path: '/register', name: 'register', component: RegisterView, meta: { title: '注册' } },
  { path: '/forgot-password', name: 'forgot-password', component: ForgotPasswordView, meta: { title: '忘记密码' } },
  { path: '/chat', name: 'chat', component: ChatView, meta: { title: '主工作台', requiresAuth: true, workspace: true } },
  { path: '/assessment', name: 'assessment', component: AssessmentView, meta: { title: '状态评估', requiresAuth: true } },
  {
    path: '/admin-dashboard',
    name: 'admin-dashboard',
    component: AdminDashboard,
    meta: { title: '管理员工作台', requiresAdmin: true, workspace: true },
  },
  {
    path: '/admin-intervention/:userId',
    name: 'admin-intervention',
    component: AdminInterventionView,
    meta: { title: '人工介入', requiresAdmin: true, workspace: true },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 };
  },
});

router.beforeEach((to) => {
  const { accessToken, user } = getStoredAuth();
  const isAuthenticated = Boolean(accessToken && user);
  const isAdmin = user?.role === 'admin';

  if (to.meta?.requiresAdmin) {
    if (!isAuthenticated) return { name: 'admin-login' };
    if (!isAdmin) return { name: 'chat' };
  }

  if (to.meta?.requiresAuth && !isAuthenticated) {
    return { name: 'login' };
  }

  return true;
});

router.afterEach((to) => {
  document.title = to.meta?.title ? `${to.meta.title} - ${APP_NAME}` : APP_NAME;
});

export default router;
