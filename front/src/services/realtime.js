import { io } from 'socket.io-client';
import { API_BASE_URL } from '@/config';
import { getAccessToken } from '@/utils/authStorage';

let socket = null;

const socketBaseUrl = () => {
  if (API_BASE_URL) return API_BASE_URL;
  return typeof window !== 'undefined' ? window.location.origin : '';
};

export const getRealtimeSocket = () => {
  const token = getAccessToken();
  if (!token) return null;

  if (socket?.connected) {
    return socket;
  }

  if (socket) {
    socket.auth = { token };
    socket.connect();
    return socket;
  }

  socket = io(socketBaseUrl(), {
    path: '/socket.io',
    auth: { token },
    transports: ['websocket', 'polling'],
    autoConnect: true,
  });

  socket.on('connect_error', (error) => {
    console.error('Socket.IO connect failed:', error?.message || error);
  });

  return socket;
};

export const joinConversationRoom = (conversationId) => {
  if (!conversationId) return;
  const activeSocket = getRealtimeSocket();
  activeSocket?.emit('join_conversation', { conversationId });
};

export const leaveConversationRoom = (conversationId) => {
  if (!conversationId || !socket) return;
  socket.emit('leave_conversation', { conversationId });
};

export const closeRealtimeSocket = () => {
  if (!socket) return;
  socket.disconnect();
  socket = null;
};
