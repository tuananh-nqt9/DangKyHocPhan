import { SlidersHorizontal } from 'lucide-react';

const filters = [
  { value: 'ALL', label: 'Tất cả' },
  { value: 'OPEN', label: 'Đang mở' },
  { value: 'CLOSED', label: 'Đã đóng' },
];

export default function CourseFilter({ value, onChange }) {
  return (
    <label className="flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-3.5">
      <SlidersHorizontal className="h-4 w-4 shrink-0 text-gray-400" aria-hidden="true" />
      <span className="sr-only">Lọc trạng thái lớp học phần</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-12 min-w-32 bg-transparent text-sm text-gray-700 outline-none"
      >
        {filters.map((filter) => (
          <option key={filter.value} value={filter.value}>
            {filter.label}
          </option>
        ))}
      </select>
    </label>
  );
}
