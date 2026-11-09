export type CourseClassStatus = 'OPEN' | 'CLOSED';

export interface ScheduleItem {
  day_of_week: 'MON' | 'TUE' | 'WED' | 'THU' | 'FRI' | 'SAT' | 'SUN';
  start_period: number;
  end_period: number;
  room: string;
}

export interface CoursePrerequisite {
  course_code: string;
  course_name: string;
  satisfied?: boolean;
}

export interface CourseClass {
  course_class_id: string;
  class_code: string;
  course_code: string;
  course_name: string;
  credits: number;
  capacity: number;
  remaining_seats: number;
  registered_count: number;
  status: CourseClassStatus;
  schedule: ScheduleItem[];
  prerequisites: CoursePrerequisite[];
}

export interface Pagination {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

export interface ApiEnvelope<T> {
  success: boolean;
  code: string;
  message: string;
  data: T;
  request_id: string;
}

export interface CourseClassListData {
  items: CourseClass[];
  pagination: Pagination;
}

export interface CourseClassUpsertRequest {
  class_code: string;
  course_code: string;
  course_name: string;
  credits: number;
  capacity: number;
  status: CourseClassStatus;
  schedule: ScheduleItem[];
  prerequisite_course_codes: string[];
}

export interface HealthData {
  status: string;
  database: string;
  api_version: string;
  features: {
    payments: boolean;
    sso: boolean;
    queue: boolean;
  };
}
