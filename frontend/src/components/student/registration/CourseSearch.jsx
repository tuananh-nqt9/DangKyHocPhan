import { Search, X } from 'lucide-react';

export default function CourseSearch({ value, onChange }) {
  return (
    <label className="relative block flex-1">
      <Search className="pointer-events-none absolute left-3.5 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" aria-hidden="true" />
      <span className="sr-only">Tìm theo mã lớp hoặc tên học phần</span>
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Tìm theo mã lớp hoặc tên học phần..."
        className="w-full rounded-xl border border-gray-200 bg-white py-3 pl-11 pr-11 text-sm text-gray-900 outline-none transition placeholder:text-gray-400 focus:border-red-400 focus:ring-2 focus:ring-red-100"
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange('')}
          className="absolute right-3 top-1/2 -translate-y-1/2 rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
          aria-label="Xóa nội dung tìm kiếm"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      )}
    </label>
  );
}
