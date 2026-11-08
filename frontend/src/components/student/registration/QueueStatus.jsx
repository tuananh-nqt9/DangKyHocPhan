import { Clock3, RefreshCw, Users } from 'lucide-react';

function formatWait(seconds) {
  if (typeof seconds !== 'number' || seconds < 0) return null;
  if (seconds < 60) return `Khoảng ${seconds} giây`;
  return `Khoảng ${Math.ceil(seconds / 60)} phút`;
}

export default function QueueStatus({
  enabled,
  state,
  loading,
  error,
  onJoin,
  onRefresh,
}) {
  if (!enabled) return null;

  const isReady = state?.status === 'READY' && Boolean(state.queue_token);
  const isWaiting = state?.status === 'WAITING';
  const canJoin = !isWaiting && !isReady;

  return (
    <section className="flex flex-col gap-4 rounded-2xl border border-amber-200 bg-amber-50 p-5 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white text-amber-700">
          {isWaiting ? <Clock3 className="h-5 w-5" aria-hidden="true" /> : <Users className="h-5 w-5" aria-hidden="true" />}
        </div>
        <div>
          <h2 className="text-sm font-semibold text-gray-900">
            {isReady ? 'Đã đến lượt đăng ký' : isWaiting ? 'Bạn đang ở trong hàng đợi' : 'Hàng đợi đăng ký đang bật'}
          </h2>
          <p className="mt-1 text-sm leading-5 text-gray-700">
            {isReady
              ? 'Bạn có thể chọn lớp và gửi yêu cầu đăng ký.'
              : isWaiting
                ? `Vị trí của bạn: ${state.position ?? 'đang cập nhật'}${formatWait(state.estimated_wait_seconds) ? ` · ${formatWait(state.estimated_wait_seconds)}` : ''}. Trạng thái tự cập nhật mỗi 3 giây.`
                : 'Tham gia hàng đợi để nhận lượt trước khi đăng ký lớp học phần.'}
          </p>
          {error && <p className="mt-2 text-sm text-red-700" role="alert">{error}</p>}
        </div>
      </div>
      <div className="flex shrink-0 gap-2 sm:justify-end">
        {isWaiting && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-amber-300 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-amber-100 disabled:opacity-60"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} aria-hidden="true" />
            Cập nhật lượt
          </button>
        )}
        {canJoin && (
          <button
            type="button"
            onClick={onJoin}
            disabled={loading}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-red-300"
          >
            {loading ? 'Đang tham gia...' : state?.status === 'EXPIRED' ? 'Tham gia lại hàng đợi' : 'Tham gia hàng đợi'}
          </button>
        )}
      </div>
    </section>
  );
}
