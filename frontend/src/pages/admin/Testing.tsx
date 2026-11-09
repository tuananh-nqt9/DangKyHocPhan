import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, Download, FileUp, FlaskConical, RefreshCw, ShieldCheck, SlidersHorizontal, TableProperties } from 'lucide-react';
import DashboardLayout from '../../components/common/DashboardLayout.jsx';
import { getAdminHealth, getAllAdminCourseClasses } from '../../services/adminService';
import type { CourseClass, HealthData } from '../../services/adminTypes';

type TestTab = 'data' | 'configuration' | 'results';

function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = '';
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"' && text[index + 1] === '"') {
        cell += '"';
        index += 1;
      } else if (character === '"') {
        quoted = false;
      } else {
        cell += character;
      }
    } else if (character === '"' && cell.length === 0) {
      quoted = true;
    } else if (character === ',') {
      row.push(cell);
      cell = '';
    } else if (character === '\n') {
      row.push(cell.replace(/\r$/, ''));
      if (row.some((value) => value.length > 0)) rows.push(row);
      row = [];
      cell = '';
    } else {
      cell += character;
    }
  }
  row.push(cell.replace(/\r$/, ''));
  if (row.some((value) => value.length > 0)) rows.push(row);
  return rows;
}

function downloadText(filename: string, content: string, mimeType: string) {
  const url = URL.createObjectURL(new Blob([content], { type: mimeType }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function getErrorMessage(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const response = error.response;
    if (typeof response === 'object' && response !== null && 'data' in response) {
      const data = response.data;
      if (typeof data === 'object' && data !== null && 'message' in data && typeof data.message === 'string') {
        return data.message;
      }
    }
  }
  return error instanceof Error ? error.message : 'Không thể tải dữ liệu.';
}

function UnavailableAction({ label }: { label: string }) {
  return (
    <button type="button" disabled title="Chưa có endpoint hoặc test runner kết nối từ frontend" className="inline-flex cursor-not-allowed items-center gap-2 rounded-lg border border-gray-200 bg-gray-100 px-4 py-2.5 text-sm font-semibold text-gray-400">
      {label} <span className="text-[10px] font-medium uppercase">Chưa hỗ trợ</span>
    </button>
  );
}

export default function Testing() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedTab = searchParams.get('tab');
  const tab: TestTab = selectedTab === 'results' || selectedTab === 'configuration' ? selectedTab : 'data';
  const [courses, setCourses] = useState<CourseClass[]>([]);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [vus, setVus] = useState('10');
  const [iterations, setIterations] = useState('1000');
  const [durationSeconds, setDurationSeconds] = useState('60');
  const [targetClassId, setTargetClassId] = useState('');
  const [csv, setCsv] = useState('');
  const [csvRows, setCsvRows] = useState<string[][]>([]);
  const [csvError, setCsvError] = useState('');

  useEffect(() => {
    let active = true;
    Promise.allSettled([getAllAdminCourseClasses(), getAdminHealth()]).then(([courseResult, healthResult]) => {
      if (!active) return;
      if (courseResult.status === 'fulfilled') {
        setCourses(courseResult.value);
        if (courseResult.value.length) setTargetClassId(courseResult.value[0].course_class_id);
      } else {
        setLoadError(getErrorMessage(courseResult.reason));
      }
      if (healthResult.status === 'fulfilled') setHealth(healthResult.value);
      else setLoadError((current) => current || getErrorMessage(healthResult.reason));
      setLoading(false);
    });
    return () => {
      active = false;
    };
  }, [targetClassId]);

  const tabs = useMemo(() => [
    { id: 'data' as const, label: 'Quản lý dữ liệu', Icon: TableProperties },
    { id: 'configuration' as const, label: 'Cấu hình kiểm thử tải', Icon: SlidersHorizontal },
    { id: 'results' as const, label: 'Kết quả kiểm thử', Icon: FlaskConical },
  ], []);
  const importedSummary = useMemo(() => {
    if (csvRows.length < 2) return null;
    const normalize = (value: string) => value.trim().toLocaleLowerCase().replace(/[\s-]+/g, '_');
    const headers = csvRows[0].map(normalize);
    const values = csvRows[1];
    const read = (...names: string[]) => {
      const index = headers.findIndex((header) => names.includes(header));
      if (index < 0) return undefined;
      const value = Number(values[index]);
      return Number.isFinite(value) ? value : undefined;
    };
    const total = read('total_requests');
    const success = read('successful_requests', 'success');
    const failure = read('failed_requests', 'failure');
    const totalRequests = total ?? (success !== undefined && failure !== undefined ? success + failure : undefined);
    const successRate = read('success_rate_percent', 'success_rate_pct') ??
      (totalRequests && success !== undefined ? (success / totalRequests) * 100 : undefined);
    return {
      totalRequests,
      success,
      failure,
      successRate,
      average: read('avg_response_time_ms', 'average_response_time_ms'),
      p95: read('p95_ms'),
      p99: read('p99_ms'),
      rps: read('rps', 'requests_per_second'),
    };
  }, [csvRows]);

  const chooseTab = (nextTab: TestTab) => {
    setSearchParams(nextTab === 'data' ? {} : { tab: nextTab }, { replace: true });
  };

  const importCsv = async (file?: File) => {
    setCsvError('');
    if (!file) return;
    if (!file.name.toLocaleLowerCase().endsWith('.csv')) {
      setCsvError('Vui lòng chọn tệp CSV.');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setCsvError('Tệp CSV không được vượt quá 5 MB.');
      return;
    }
    try {
      const text = await file.text();
      const rows = parseCsv(text);
      if (rows.length < 1 || rows[0].length < 1) throw new Error('Tệp CSV không có dữ liệu hợp lệ.');
      setCsv(text);
      setCsvRows(rows);
    } catch (error) {
      setCsvError(error instanceof Error ? error.message : 'Không đọc được tệp CSV.');
      setCsv('');
      setCsvRows([]);
    }
  };

  const exportCsv = () => {
    if (!csv) return;
    downloadText('ket-qua-kiem-thu.csv', csv, 'text/csv;charset=utf-8');
  };

  const exportConfiguration = () => {
    const target = courses.find((course) => course.course_class_id === targetClassId);
    const config = {
      scenario: 'registration',
      vus: Number(vus),
      iterations: Number(iterations),
      duration_seconds: Number(durationSeconds),
      target_course_class_id: targetClassId,
      target_class_code: target?.class_code || '',
    };
    downloadText('cau-hinh-kiem-thu.json', JSON.stringify(config, null, 2), 'application/json;charset=utf-8');
  };

  return (
    <DashboardLayout role="ADMIN" pageTitle="Trung tâm kiểm thử" stickyHeader>
      <div className="space-y-6">
        <div>
          <p className="text-sm font-medium text-red-700">Công cụ vận hành</p>
          <h2 className="mt-1 text-2xl font-bold text-gray-900">CHƯA PHÁT TRIỂN</h2>
          <p className="mt-1 text-sm text-gray-500">Chỉ kích hoạt thao tác khi có API hoặc test runner được backend hỗ trợ.</p>
        </div>

        <div className="flex gap-1 overflow-x-auto border-b border-gray-200" role="tablist" aria-label="Các khu vực kiểm thử">
          {tabs.map(({ id, label, Icon }) => (
            <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => chooseTab(id)} className={`inline-flex shrink-0 items-center gap-2 border-b-2 px-4 py-3 text-sm font-semibold ${
              tab === id ? 'border-red-600 text-red-700' : 'border-transparent text-gray-500 hover:text-gray-800'
            }`}>
              <Icon className="h-4 w-4" aria-hidden="true" /> {label}
            </button>
          ))}
        </div>

        {loadError && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{loadError}</p>}

        {tab === 'data' && (
          <div className="space-y-5">
            <section className="rounded-xl border border-amber-200 bg-amber-50 p-5">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" />
                <div>
                  <h3 className="font-semibold text-amber-900">Các thao tác dữ liệu hiện chỉ có CLI</h3>
                  <p className="mt-1 text-sm leading-6 text-amber-800">
                    Seed, reset, chuẩn bị token và kiểm tra invariants chưa có API/test runner cho frontend.
                    Để tránh chạy lệnh hệ điều hành hoặc giả lập kết quả, các nút này chưa được kích hoạt.
                  </p>
                </div>
              </div>
            </section>

            <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {[
                { label: 'Khởi tạo dữ liệu kiểm thử', Icon: TableProperties },
                { label: 'Reset dữ liệu kiểm thử', Icon: RefreshCw },
                { label: 'Chuẩn bị token', Icon: ShieldCheck },
                { label: 'Kiểm tra toàn vẹn dữ liệu', Icon: CheckCircle2 },
              ].map(({ label, Icon }) => (
                <article key={label} className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                  <Icon className="h-5 w-5 text-gray-400" aria-hidden="true" />
                  <h3 className="mt-3 font-semibold text-gray-900">{label}</h3>
                  <p className="mt-1 min-h-10 text-xs leading-5 text-gray-500">Chỉ chạy được từ công cụ CLI backend trong môi trường kiểm thử.</p>
                  <div className="mt-4"><UnavailableAction label="Chưa khả dụng" /></div>
                </article>
              ))}
            </section>
            <section className="rounded-xl border border-gray-200 bg-white p-5">
              <h3 className="font-semibold text-gray-900">Trạng thái API</h3>
              {loading ? <p className="mt-3 text-sm text-gray-500">Đang kiểm tra API...</p> : health ? (
                <p className="mt-3 inline-flex items-center gap-2 text-sm text-green-700">
                  <CheckCircle2 className="h-4 w-4" /> API {health.status} · CSDL {health.database} · v{health.api_version}
                </p>
              ) : <p className="mt-3 text-sm text-gray-500">Không có thông tin health.</p>}
            </section>
          </div>
        )}

        {tab === 'configuration' && (
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(280px,0.7fr)]">
            <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <h3 className="font-semibold text-gray-900">Cấu hình kiểm thử tải</h3>
              <p className="mt-1 text-sm text-gray-500">Tham số chỉ được xuất thành tệp cấu hình; frontend không tự chạy k6.</p>
              <div className="mt-5 grid gap-4 sm:grid-cols-2">
                <label className="text-sm font-medium text-gray-700">Virtual Users (VUs)
                  <input type="number" min={1} max={1000} step={1} value={vus} onChange={(event) => setVus(event.target.value)} className="mt-1.5 w-full rounded-lg border border-gray-200 px-3 py-2.5 outline-none focus:border-red-400" />
                </label>
                <label className="text-sm font-medium text-gray-700">Iterations
                  <input type="number" min={1} max={1000000} step={1} value={iterations} onChange={(event) => setIterations(event.target.value)} className="mt-1.5 w-full rounded-lg border border-gray-200 px-3 py-2.5 outline-none focus:border-red-400" />
                </label>
                <label className="text-sm font-medium text-gray-700">Thời gian (giây)
                  <input type="number" min={1} max={86400} step={1} value={durationSeconds} onChange={(event) => setDurationSeconds(event.target.value)} className="mt-1.5 w-full rounded-lg border border-gray-200 px-3 py-2.5 outline-none focus:border-red-400" />
                </label>
                <label className="text-sm font-medium text-gray-700">Lớp học phần mục tiêu
                  <select value={targetClassId} onChange={(event) => setTargetClassId(event.target.value)} disabled={loading || courses.length === 0} className="mt-1.5 w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 outline-none focus:border-red-400">
                    {courses.length === 0 && <option value="">Không có lớp học phần</option>}
                    {courses.map((course) => <option key={course.course_class_id} value={course.course_class_id}>{course.class_code} · {course.course_name}</option>)}
                  </select>
                </label>
                <div className="sm:col-span-2">
                  <p className="text-sm font-medium text-gray-700">Kịch bản</p>
                  <div className="mt-1.5 rounded-lg border border-gray-200 bg-gray-50 px-3 py-3 text-sm text-gray-700">
                    Đăng ký học phần — POST /api/v1/register
                  </div>
                </div>
              </div>
              <button type="button" onClick={exportConfiguration} disabled={!targetClassId || !Number.isInteger(Number(vus)) || Number(vus) < 1 || Number(vus) > 1000 || !Number.isInteger(Number(iterations)) || Number(iterations) < 1 || Number(iterations) > 1000000 || !Number.isInteger(Number(durationSeconds)) || Number(durationSeconds) < 1 || Number(durationSeconds) > 86400} className="mt-5 inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50">
                <Download className="h-4 w-4" /> Tải cấu hình JSON
              </button>
            </section>
            <aside className="h-fit rounded-xl border border-amber-200 bg-amber-50 p-5">
              <AlertTriangle className="h-5 w-5 text-amber-700" />
              <h3 className="mt-3 font-semibold text-amber-900">Chưa có test runner kết nối</h3>
              <p className="mt-2 text-sm leading-6 text-amber-800">
                API hiện tại không cung cấp endpoint chạy k6. Chạy tải cần runner/CLI được quản lý riêng; trang này không khởi chạy tiến trình trên máy chủ frontend.
              </p>
              <div className="mt-4"><UnavailableAction label="Chạy kiểm thử" /></div>
            </aside>
          </div>
        )}

        {tab === 'results' && (
          <div className="space-y-5">
            <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h3 className="font-semibold text-gray-900">Kết quả và lịch sử kiểm thử</h3>
                  <p className="mt-1 text-sm text-gray-500">Backend hiện chưa có API lưu/truy vấn kết quả. Có thể nạp CSV kết quả đã có để xem và xuất lại.</p>
                </div>
                <div className="flex gap-2">
                  <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50">
                    <FileUp className="h-4 w-4" /> Nhập CSV
                    <input type="file" accept=".csv,text/csv" className="sr-only" onChange={(event) => importCsv(event.target.files?.[0])} />
                  </label>
                  <button type="button" onClick={exportCsv} disabled={!csv} className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50">
                    <Download className="h-4 w-4" /> Xuất CSV
                  </button>
                </div>
              </div>
              {csvError && <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{csvError}</p>}
            </section>

            {csvRows.length ? (
              <>
                {importedSummary && Object.values(importedSummary).some((value) => value !== undefined) && (
                  <section className="space-y-4">
                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                      {[
                        ['Tổng request', importedSummary.totalRequests],
                        ['Thành công', importedSummary.success],
                        ['Thất bại', importedSummary.failure],
                        ['Tỷ lệ thành công', importedSummary.successRate === undefined ? undefined : `${importedSummary.successRate.toFixed(2)}%`],
                        ['Average (ms)', importedSummary.average],
                        ['P95 (ms)', importedSummary.p95],
                        ['P99 (ms)', importedSummary.p99],
                        ['RPS', importedSummary.rps],
                      ].filter(([, value]) => value !== undefined).map(([label, value]) => (
                        <article key={label} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                          <p className="text-xs text-gray-500">{label}</p>
                          <p className="mt-2 text-2xl font-bold text-gray-900">
                            {typeof value === 'number' ? value.toLocaleString('vi-VN', { maximumFractionDigits: 2 }) : value}
                          </p>
                        </article>
                      ))}
                    </div>
                    {(importedSummary.success !== undefined || importedSummary.failure !== undefined) && (
                      <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                        <h3 className="font-semibold text-gray-900">Tổng quan request từ CSV</h3>
                        <div className="mt-4 space-y-3">
                          {[
                            ['Thành công', importedSummary.success, 'bg-green-500'],
                            ['Thất bại', importedSummary.failure, 'bg-red-500'],
                          ].filter(([, value]) => typeof value === 'number').map(([label, value, color]) => {
                            const total = (importedSummary.success || 0) + (importedSummary.failure || 0);
                            const width = total ? ((Number(value) / total) * 100) : 0;
                            return (
                              <div key={label}>
                                <div className="mb-1 flex justify-between text-xs text-gray-600"><span>{label}</span><span>{Number(value).toLocaleString('vi-VN')}</span></div>
                                <div className="h-2 overflow-hidden rounded-full bg-gray-100"><div className={`h-full rounded-full ${color}`} style={{ width: `${width}%` }} /></div>
                              </div>
                            );
                          })}
                        </div>
                      </section>
                    )}
                  </section>
                )}
                <section className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
                  <div className="border-b border-gray-100 px-5 py-3 text-sm text-gray-600">{csvRows.length - 1} dòng dữ liệu đã nhập</div>
                  <div className="overflow-auto">
                    <table className="w-full min-w-max text-left text-xs">
                      <thead className="bg-gray-50 font-semibold text-gray-700">
                        <tr>{csvRows[0].map((heading, index) => <th key={`${heading}-${index}`} className="whitespace-nowrap px-3 py-2">{heading || `Cột ${index + 1}`}</th>)}</tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {csvRows.slice(1, 101).map((row, rowIndex) => (
                          <tr key={rowIndex} className="text-gray-600">
                            {csvRows[0].map((_, columnIndex) => <td key={columnIndex} className="whitespace-nowrap px-3 py-2">{row[columnIndex] || ''}</td>)}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {csvRows.length > 101 && <p className="border-t border-gray-100 px-5 py-2 text-xs text-gray-500">Hiển thị 100 dòng đầu tiên.</p>}
                </section>
              </>
            ) : (
              <section className="rounded-xl border border-dashed border-gray-300 bg-white px-6 py-14 text-center">
                <FlaskConical className="mx-auto h-10 w-10 text-gray-300" />
                <h3 className="mt-4 font-semibold text-gray-900">Chưa có dữ liệu kiểm thử</h3>
                <p className="mx-auto mt-1 max-w-lg text-sm text-gray-500">Không có endpoint kết quả hoặc lịch sử trong API hiện tại. Các chỉ số request, success/failure, latency, P95/P99 và RPS chỉ hiển thị khi có kết quả thật.</p>
                <p className="mt-3 text-xs text-gray-400">Có thể nhập CSV kết quả đã xuất từ test runner để xem dữ liệu.</p>
              </section>
            )}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
