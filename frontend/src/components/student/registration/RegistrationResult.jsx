import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { CheckCircle2, LoaderCircle, RotateCw, X, XCircle } from 'lucide-react';

const AUTO_CLOSE_MS = 6000;

export default function RegistrationResult({
  results = [],
  cancelFeedback,
  registeringIds,
  onRetry,
  onClose,
}) {
  const hasRegistrationResults = results.length > 0;
  const hasPending = results.some((result) => registeringIds.has(result.courseId));
  useEffect(() => {
    if (hasPending) return undefined;
    if (!hasRegistrationResults && !cancelFeedback) return undefined;
    const timerId = window.setTimeout(onClose, AUTO_CLOSE_MS);
    return () => window.clearTimeout(timerId);
  }, [results, cancelFeedback, hasPending, hasRegistrationResults, onClose]);

  if (!hasRegistrationResults && !cancelFeedback) return null;

  const successfulCount = results.filter((result) => result.type === 'success').length;
  const notificationType = cancelFeedback?.type ||
    (results.some((result) => result.type === 'error') ? 'error' : 'success');

  return createPortal(
    <aside
      role={notificationType === 'error' ? 'alert' : 'status'}
      aria-label="Thông báo đăng ký học phần"
      className="fixed right-4 top-4 z-[100] w-[calc(100vw-2rem)] max-w-md"
    >
      <section
        className={`overflow-hidden rounded-xl border bg-white shadow-xl ${
          notificationType === 'error' ? 'border-red-200' : 'border-green-200'
        }`}
      >
        <div className="flex items-start gap-3 p-4">
          {cancelFeedback ? (
            notificationType === 'error'
              ? <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-600" aria-hidden="true" />
              : <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-green-600" aria-hidden="true" />
          ) : hasPending ? (
            <LoaderCircle className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-gray-500" aria-hidden="true" />
          ) : notificationType === 'error' ? (
            <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-600" aria-hidden="true" />
          ) : (
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-green-600" aria-hidden="true" />
          )}

          <div className="min-w-0 flex-1">
            {cancelFeedback ? (
              <>
                <p className="text-sm font-semibold text-gray-900">
                  {notificationType === 'success' ? 'Đã xử lý yêu cầu' : 'Không thể hoàn tất yêu cầu'}
                </p>
                <p className={`mt-1 text-sm ${notificationType === 'error' ? 'text-red-700' : 'text-green-700'}`}>
                  {cancelFeedback.message}
                </p>
                {cancelFeedback.requestId && (
                  <p className="mt-1 text-xs text-gray-500">Mã yêu cầu: {cancelFeedback.requestId}</p>
                )}
              </>
            ) : (
              <>
                <p className="text-sm font-semibold text-gray-900">
                  {hasPending
                    ? 'Đang xử lý đăng ký'
                    : `Kết quả đăng ký: ${successfulCount}/${results.length} lớp thành công`}
                </p>
                <div className="mt-2 max-h-56 space-y-2 overflow-y-auto">
                  {results.map((result) => {
                    const pending = registeringIds.has(result.courseId);
                    const successful = result.type === 'success';
                    return (
                      <div key={result.courseId} className="border-t border-gray-100 pt-2">
                        <p className="text-xs font-semibold text-gray-800">
                          {result.classCode} · {result.courseName}
                        </p>
                        <p className={`mt-0.5 text-xs ${successful ? 'text-green-700' : pending ? 'text-gray-500' : 'text-red-700'}`}>
                          {pending ? 'Đang gửi yêu cầu...' : result.message}
                        </p>
                        {result.requestId && (
                          <p className="mt-0.5 text-xs text-gray-500">Mã yêu cầu: {result.requestId}</p>
                        )}
                        {!successful && result.retryable && !pending && (
                          <button
                            type="button"
                            onClick={() => onRetry(result.courseId)}
                            className="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-red-700 hover:text-red-900"
                          >
                            <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
                            Thử lại
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
            aria-label="Đóng thông báo"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </section>
    </aside>,
    document.body,
  );
}
