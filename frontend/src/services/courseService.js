import apiClient from './apiClient';

export async function getCourseClasses({ page = 1, pageSize = 100 } = {}) {
  const response = await apiClient.get('/v1/course-classes', {
    params: {
      page,
      page_size: pageSize,
    },
  });
  return response.data;
}

export async function getCourseClass(courseClassId) {
  const response = await apiClient.get(`/v1/course-classes/${encodeURIComponent(courseClassId)}`);
  return response.data;
}
