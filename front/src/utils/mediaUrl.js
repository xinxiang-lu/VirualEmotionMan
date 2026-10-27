import { API_BASE_URL } from '@/config';

const ABSOLUTE_URL_PATTERN = /^https?:\/\//i;

const resolveBaseOrigin = () => {
  if (API_BASE_URL) {
    return API_BASE_URL;
  }

  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin;
  }

  return '';
};

export const resolveMediaUrl = (url) => {
  if (!url) return '';
  if (ABSOLUTE_URL_PATTERN.test(url)) return url;

  const baseOrigin = resolveBaseOrigin();
  if (!baseOrigin) {
    return url;
  }

  return new URL(url, baseOrigin).toString();
};

