import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Download, FileUp, FlaskConical, SlidersHorizontal } from 'lucide-react';
import DashboardLayout from '../../components/common/DashboardLayout.jsx';
import { getAllAdminCourseClasses } from '../../services/adminService';
import type { CourseClass } from '../../services/adminTypes';

type TestTab = 'configuration' | 'results';
const TestingLineChart = lazy(() => import('./TestingLineChart'));

const chartMetricDefinitions = [
  { label: 'Tổng request', aliases: ['total_requests'], color: '#334155' },
  { label: 'Request thành công', aliases: ['successful_requests', 'success'], color: '#16a34a' },
  { label: 'Request thất bại', aliases: ['failed_requests', 'failure'], color: '#dc2626' },
  { label: 'Tỷ lệ thành công (%)', aliases: ['success_rate_percent', 'success_rate_pct'], color: '#7c3aed' },
  { label: 'Average response time (ms)', aliases: ['avg_response_time_ms', 'average_response_time_ms'], color: '#2563eb' },
  { label: 'P95 (ms)', aliases: ['p95_ms'], color: '#ea580c' },
  { label: 'P99 (ms)', aliases: ['p99_ms'], color: '#be123c' },
  { label: 'RPS', aliases: ['rps', 'requests_per_second'], color: '#0891b2' },
] as const;

function normalizeHeader(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/[\s-]+/g, '_');
}

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

export default function Testing() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedTab = searchParams.get('tab');
  const tab: TestTab = selectedTab === 'results' ? 'results' : 'configuration';
  const [courses, setCourses] = useState<CourseClass[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [vus, setVus] = useState('10');
  const [iterations, setIterations] = useState('1000');
  const [durationSeconds, setDurationSeconds] = useState('60');
  const [targetClassId, setTargetClassId] = useState('');
  const [csv, setCsv] = useState('');
  const [csvRows, setCsvRows] = useState<string[][]>([]);
  const [csvError, setCsvError] = useState('');
  const [selectedChartMetric, setSelectedChartMetric] = useState('');

  useEffect(() => {
    let active = true;
    getAllAdminCourseClasses().then((loadedCourses) => {
      if (!active) return;
      setCourses(loadedCourses);
      if (loadedCourses.length) setTargetClassId(loadedCourses[0].course_class_id);
    }).catch((error: unknown) => {
      if (active) setLoadError(getErrorMessage(error));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => {
      active = false;
    };
  }, []);

  const tabs = useMemo(() => [
    { id: 'configuration' as const, label: 'Cấu hình kiểm thử tải', Icon: SlidersHorizontal },
    { id: 'results' as const, label: 'Kết quả kiểm thử', Icon: FlaskConical },
  ], []);
  const importedSummary = useMemo(() => {
    if (csvRows.length < 2) return null;
    const headers = csvRows[0].map(normalizeHeader);
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
  const chartMetrics = useMemo(() => {
    if (csvRows.length < 2) return [];
    const headers = csvRows[0].map(normalizeHeader);
    return chartMetricDefinitions.flatMap((definition) => {
      const index = headers.findIndex((header) => definition.aliases.some((alias) => alias === header));
      if (index < 0 || !csvRows.slice(1).some((row) => row[index]?.trim() !== '' && Number.isFinite(Number(row[index])))) {
        return [];
      }
      return [{ key: headers[index], index, label: definition.label, color: definition.color }];
    });
  }, [csvRows]);
  const selectedMetric = chartMetrics.find((metric) => metric.key === selectedChartMetric) ?? chartMetrics[0];
  const chartData = useMemo(() => {
    if (csvRows.length < 2 || !selectedMetric) return [];
    const headers = csvRows[0].map(normalizeHeader);
    const labelIndex = headers.findIndex((header) =>
      ['run_at', 'timestamp', 'time', 'date', 'run_id', 'run', 'iteration'].includes(header),
    );
    return csvRows.slice(1)
      .map((row, index) => {
        const rawValue = row[selectedMetric.index]?.trim();
        const value = rawValue ? Number(rawValue) : Number.NaN;
        const label = labelIndex >= 0 && row[labelIndex]?.trim()
          ? row[labelIndex].trim()
          : `Lượt ${index + 1}`;
        return { label, value };
      })
      .filter((point) => Number.isFinite(point.value));
  }, [csvRows, selectedMetric]);

  const chooseTab = (nextTab: TestTab) => {
    setSearchParams({ tab: nextTab }, { replace: true });
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
        <div className="flex gap-1 overflow-x-auto border-b border-gray-200" role="tablist" aria-label="Các khu vực kiểm thử">
          {tabs.map(({ id, label, Icon }) => (
            <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => chooseTab(id)} className={`inline-flex shrink-0 items-center gap-2 border-b-2 px-4 py-3 text-sm font-semibold ${
              tab === id ? 'border-red-600 text-red-700' : 'border-transparent text-gray-500 hover:text-gray-800'
            }`}>
              <Icon className="h-4 w-4" aria-hidden="true" /> {label}
            </button>
          ))}
        </div>

        {loadError && <p role="alert" className="border border-red-200 bg-red-50 p-4 text-sm text-red-700">{loadError}</p>}
        {tab === 'configuration' && (
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(280px,0.7fr)]">
            <section className="border border-gray-200 bg-white p-5 shadow-sm">
              <h3 className="font-semibold text-gray-900">Cấu hình kiểm thử tải</h3>
              <div className="mt-5 grid gap-4 sm:grid-cols-2">
                <label className="text-sm font-medium text-gray-700">Virtual Users (VUs)
                  <input type="number" min={1} max={1000} step={1} value={vus} onChange={(event) => setVus(event.target.value)} className="mt-1.5 w-full border border-gray-200 px-3 py-2.5 outline-none focus:border-red-400" />
                </label>
                <label className="text-sm font-medium text-gray-700">Iterations
                  <input type="number" min={1} max={1000000} step={1} value={iterations} onChange={(event) => setIterations(event.target.value)} className="mt-1.5 w-full border border-gray-200 px-3 py-2.5 outline-none focus:border-red-400" />
                </label>
                <label className="text-sm font-medium text-gray-700">Thời gian (giây)
                  <input type="number" min={1} max={86400} step={1} value={durationSeconds} onChange={(event) => setDurationSeconds(event.target.value)} className="mt-1.5 w-full border border-gray-200 px-3 py-2.5 outline-none focus:border-red-400" />
                </label>
                <label className="text-sm font-medium text-gray-700">Lớp học phần mục tiêu
                  <select value={targetClassId} onChange={(event) => setTargetClassId(event.target.value)} disabled={loading || courses.length === 0} className="mt-1.5 w-full border border-gray-200 bg-white px-3 py-2.5 outline-none focus:border-red-400">
                    {courses.length === 0 && <option value="">Không có lớp học phần</option>}
                    {courses.map((course) => <option key={course.course_class_id} value={course.course_class_id}>{course.class_code} · {course.course_name}</option>)}
                  </select>
                </label>
              </div>
              <button type="button" onClick={exportConfiguration} disabled={!targetClassId || !Number.isInteger(Number(vus)) || Number(vus) < 1 || Number(vus) > 1000 || !Number.isInteger(Number(iterations)) || Number(iterations) < 1 || Number(iterations) > 1000000 || !Number.isInteger(Number(durationSeconds)) || Number(durationSeconds) < 1 || Number(durationSeconds) > 86400} className="mt-5 inline-flex items-center gap-2 bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50">
                <Download className="h-4 w-4" /> Tải cấu hình JSON
              </button>
            </section>
          </div>
        )}

        {tab === 'results' && (
          <div className="space-y-5">
            <section className="border border-gray-200 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h3 className="font-semibold text-gray-900">Kết quả và lịch sử kiểm thử</h3>
                </div>
                <div className="flex gap-2">
                  <label className="inline-flex cursor-pointer items-center gap-2 border border-gray-200 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50">
                    <FileUp className="h-4 w-4" /> Nhập CSV
                    <input type="file" accept=".csv,text/csv" className="sr-only" onChange={(event) => importCsv(event.target.files?.[0])} />
                  </label>
                  <button type="button" onClick={exportCsv} disabled={!csv} className="inline-flex items-center gap-2 bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50">
                    <Download className="h-4 w-4" /> Xuất CSV
                  </button>
                </div>
              </div>
              {csvError && <p role="alert" className="mt-4 border border-red-200 bg-red-50 p-3 text-sm text-red-700">{csvError}</p>}
            </section>

            {csvRows.length ? (
              <>
                <section className="border border-gray-200 bg-white p-5 shadow-sm">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h3 className="font-semibold text-gray-900">Biểu đồ kết quả kiểm thử</h3>
                      <p className="mt-1 text-sm text-gray-500">Chọn chỉ số để xem xu hướng theo các dòng dữ liệu trong CSV.</p>
                    </div>
                    {chartMetrics.length > 0 && (
                      <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
                        Chỉ số
                        <select
                          value={selectedMetric?.key ?? ''}
                          onChange={(event) => setSelectedChartMetric(event.target.value)}
                          className="border border-gray-200 bg-white px-3 py-2 outline-none focus:border-red-400"
                        >
                          {chartMetrics.map((metric) => (
                            <option key={metric.key} value={metric.key}>{metric.label}</option>
                          ))}
                        </select>
                      </label>
                    )}
                  </div>
                  {selectedMetric && chartData.length > 0 ? (
                    <div className="mt-5 h-80 w-full">
                      <Suspense fallback={<div className="h-full animate-pulse bg-gray-50" role="status">Đang tải biểu đồ...</div>}>
                        <TestingLineChart
                          data={chartData}
                          metricLabel={selectedMetric.label}
                          color={selectedMetric.color}
                        />
                      </Suspense>
                    </div>
                  ) : (
                    <p className="mt-5 border border-dashed border-gray-300 bg-gray-50 px-4 py-8 text-center text-sm text-gray-500">
                      CSV chưa có cột số liệu kiểm thử phù hợp để vẽ biểu đồ.
                    </p>
                  )}
                </section>
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
                        <article key={label} className="border border-gray-200 bg-white p-4 shadow-sm">
                          <p className="text-xs text-gray-500">{label}</p>
                          <p className="mt-2 text-2xl font-bold text-gray-900">
                            {typeof value === 'number' ? value.toLocaleString('vi-VN', { maximumFractionDigits: 2 }) : value}
                          </p>
                        </article>
                      ))}
                    </div>
                    {(importedSummary.success !== undefined || importedSummary.failure !== undefined) && (
                      <section className="border border-gray-200 bg-white p-5 shadow-sm">
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
                                <div className="h-2 overflow-hidden bg-gray-100"><div className={`h-full ${color}`} style={{ width: `${width}%` }} /></div>
                              </div>
                            );
                          })}
                        </div>
                      </section>
                    )}
                  </section>
                )}
                <section className="overflow-hidden border border-gray-200 bg-white shadow-sm">
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
              <section className="border border-dashed border-gray-300 bg-white px-6 py-14 text-center">
                <FlaskConical className="mx-auto h-10 w-10 text-gray-300" />
                <h3 className="mt-4 font-semibold text-gray-900">Chưa có dữ liệu kiểm thử</h3>
              </section>
            )}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
