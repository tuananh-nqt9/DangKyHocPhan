import apiClient from './apiClient';

export async function getMyRegistrations({ page = 1, pageSize = 1, status = 'ACTIVE' } = {}) {
  const response = await apiClient.get('/v1/registrations/me', {
    params: {
      page,
      page_size: pageSize,
      status,
    },
  });
  return response.data;
}
