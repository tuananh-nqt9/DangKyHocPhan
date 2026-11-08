import apiClient from './apiClient';

export async function joinQueue() {
  const response = await apiClient.post('/v1/queue/join', {});
  return response.data;
}

export async function getQueueStatus() {
  const response = await apiClient.get('/v1/queue/status');
  return response.data;
}

export function saveQueueState(queueState) {
  if (queueState?.status === 'READY' && queueState.queue_token) {
    sessionStorage.setItem('queue_token', queueState.queue_token);
  } else {
    sessionStorage.removeItem('queue_token');
  }
}
