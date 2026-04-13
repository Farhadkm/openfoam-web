"use client";

type AlertProps = {
  open: boolean;
  title?: string;
  message: string;
  buttonLabel?: string;
  onClose: () => void;
};

export function ThemeAlertDialog({
  open,
  title = "Notice",
  message,
  buttonLabel = "OK",
  onClose,
}: AlertProps) {
  if (!open) return null;
  return (
    <div className="modal-backdrop theme-dialog-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal-content theme-dialog-panel"
        style={{ maxWidth: 420 }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="theme-alert-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="theme-alert-title" className="modal-title">
          {title}
        </h3>
        <p style={{ margin: "0 0 20px", fontSize: 14, color: "var(--text-secondary)", lineHeight: 1.5 }}>
          {message}
        </p>
        <div className="modal-actions">
          <button type="button" className="sm" onClick={onClose}>
            {buttonLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

type ConfirmProps = {
  open: boolean;
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ThemeConfirmDialog({
  open,
  title = "Confirm",
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmProps) {
  if (!open) return null;
  return (
    <div className="modal-backdrop theme-dialog-backdrop" role="presentation" onClick={onCancel}>
      <div
        className="modal-content theme-dialog-panel"
        style={{ maxWidth: 440 }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="theme-confirm-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="theme-confirm-title" className="modal-title">
          {title}
        </h3>
        <p style={{ margin: "0 0 20px", fontSize: 14, color: "var(--text-secondary)", lineHeight: 1.5 }}>
          {message}
        </p>
        <div className="modal-actions">
          <button type="button" className="secondary sm" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className={danger ? "sm danger" : "sm"}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
