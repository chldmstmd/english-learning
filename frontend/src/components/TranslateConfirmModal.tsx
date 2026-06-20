interface TranslateConfirmModalProps {
  isOpen: boolean;
  title: string;
  wordCount: number;
  onConfirm: () => void;
  onCancel: () => void;
}

export function TranslateConfirmModal({
  isOpen,
  title,
  wordCount,
  onConfirm,
  onCancel,
}: TranslateConfirmModalProps): JSX.Element | null {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="translate-confirm-title"
        aria-describedby="translate-confirm-description"
        className="bg-white rounded-xl shadow-xl p-6 max-w-sm w-full mx-4"
      >
        <h3 id="translate-confirm-title" className="text-base font-semibold text-gray-900 mb-1">
          确认预翻译
        </h3>
        <p id="translate-confirm-description" className="text-sm text-gray-500 mb-4">
          预翻译会消耗 AI 配额，请确认。
        </p>

        <div className="bg-gray-50 rounded-lg px-4 py-3 mb-5">
          <p className="text-sm font-medium text-gray-800 line-clamp-2">{title}</p>
          <p className="text-xs text-gray-400 mt-1">{wordCount.toLocaleString()} 词</p>
        </div>

        <div className="flex gap-3 justify-end">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-500 rounded-lg hover:bg-blue-600 transition-colors"
          >
            确认翻译
          </button>
        </div>
      </div>
    </div>
  );
}

export default TranslateConfirmModal;
