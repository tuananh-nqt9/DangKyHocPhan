import apiClient from './apiClient.js';
import type {
  ApiEnvelope,
  CourseClass,
  CourseClassListData,
  CourseClassStatus,
  CourseClassUpsertRequest,
  HealthData,
} from './adminTypes';

export async function getAdminCourseClasses({
  page = 1,
  pageSize = 100,
  query,
}: {
  page?: number;
  pageSize?: number;
  query?: string;
} = {}): Promise<ApiEnvelope<CourseClassListData>> {
  const response = await apiClient.get<ApiEnvelope<CourseClassListData>>('/v1/course-classes', {
    params: {
      page,
      page_size: pageSize,
      ...(query ? { q: query } : {}),
    },
  });
  return response.data;
}

export async function getAllAdminCourseClasses(query?: string): Promise<CourseClass[]> {
  const firstPage = await getAdminCourseClasses({ page: 1, pageSize: 100, query });
  if (!Array.isArray(firstPage.data?.items) || !firstPage.data.pagination) {
    throw new Error('Dữ liệu danh sách lớp học phần không hợp lệ.');
  }

  const items = [...firstPage.data.items];
  for (let page = 2; page <= firstPage.data.pagination.total_pages; page += 1) {
    const response = await getAdminCourseClasses({ page, pageSize: 100, query });
    if (!Array.isArray(response.data?.items)) {
      throw new Error('Dữ liệu danh sách lớp học phần không hợp lệ.');
    }
    items.push(...response.data.items);
  }
  return items;
}

export async function getAdminCourseClass(courseClassId: string): Promise<CourseClass> {
  const response = await apiClient.get<ApiEnvelope<{ course_class: CourseClass }>>(
    `/v1/course-classes/${encodeURIComponent(courseClassId)}`,
  );
  return response.data.data.course_class;
}

export async function createCourseClass(payload: CourseClassUpsertRequest): Promise<CourseClass> {
  const response = await apiClient.post<ApiEnvelope<{ course_class: CourseClass }>>(
    '/v1/admin/course-classes',
    payload,
  );
  return response.data.data.course_class;
}

export async function updateCourseClass(
  courseClassId: string,
  payload: CourseClassUpsertRequest,
): Promise<CourseClass> {
  const response = await apiClient.put<ApiEnvelope<{ course_class: CourseClass }>>(
    `/v1/admin/course-classes/${encodeURIComponent(courseClassId)}`,
    payload,
  );
  return response.data.data.course_class;
}

export async function updateCourseClassStatus(
  courseClassId: string,
  status: CourseClassStatus,
): Promise<CourseClass> {
  const response = await apiClient.patch<ApiEnvelope<{ course_class: CourseClass }>>(
    `/v1/admin/course-classes/${encodeURIComponent(courseClassId)}/status`,
    { status },
  );
  return response.data.data.course_class;
}

export async function getAdminHealth(): Promise<HealthData> {
  const response = await apiClient.get<ApiEnvelope<HealthData>>('/v1/health');
  return response.data.data;
}
