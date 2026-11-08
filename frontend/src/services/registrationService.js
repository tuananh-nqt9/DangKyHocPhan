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

export async function registerCourseClass(payload, idempotencyKey, queueToken) {
  const headers = {
    'Idempotency-Key': idempotencyKey,
  };
  if (queueToken) {
    headers['X-Queue-Token'] = queueToken;
  }

  const response = await apiClient.post('/v1/register', payload, { headers });
  return response.data;
}

export async function cancelRegistration(registrationId, idempotencyKey) {
  const response = await apiClient.delete(
    `/v1/registrations/${encodeURIComponent(registrationId)}`,
    {
      headers: {
        'Idempotency-Key': idempotencyKey,
      },
    },
  );
  return response.data;
}
