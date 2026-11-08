import apiClient from './apiClient';

export async function getHealth() {
  const response = await apiClient.get('/v1/health');
  return response.data;
}
