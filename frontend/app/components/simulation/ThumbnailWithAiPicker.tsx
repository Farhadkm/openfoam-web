"use client";

import { useEffect, useMemo, useState } from "react";
import { generateAiThumbnail } from "@/lib/api";

type Props = {
  label?: string;
  /** Shown when `value` is null (e.g. existing server thumbnail on edit). */
  remotePreviewUrl?: string | null;
  /** Selected or AI-generated file sent to the API on save/create. */
  value: File | null;
  onChange: (file: File | null) => void;
  title: string;
  description: string;
};

export function ThumbnailWithAiPicker({
  label = "Thumbnail Image",
  remotePreviewUrl = null,
  value,
  onChange,
  title,
  description,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const blobUrl = useMemo(() => (value ? URL.createObjectURL(value) : null), [value]);
  useEffect(() => {
    return () => {
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [blobUrl]);

  const displayUrl = blobUrl ?? remotePreviewUrl ?? null;

  const runAi = async () => {
    setNotice(null);
    if (!title.trim() && !description.trim()) {
      setNotice("Add a title or description so the generated image matches your simulation.");
      return;
    }
    setBusy(true);
    try {
      const file = await generateAiThumbnail(title, description);
      onChange(file);
      setNotice(null);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Thumbnail generation failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="form-group thumb-picker-group">
      <label>{label}</label>
      <div className="thumb-edit-stack">
        <div className="thumb-edit-preview-wrap">
          {displayUrl ? (
            <img
              src={displayUrl}
              alt="Thumbnail preview"
              className="thumb-edit-preview-full"
            />
          ) : (
            <div className="thumb-edit-preview-full thumb-edit-preview-full--empty" aria-hidden>
              <span>No image yet</span>
            </div>
          )}
          <button
            type="button"
            className="ai-thumb-btn ai-thumb-btn--overlay"
            onClick={() => void runAi()}
            disabled={busy}
            aria-label="Generate thumbnail with AI from title and description"
            title="Generate thumbnail from title and description using AI"
          >
            {busy ? (
              <svg className="spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" />
                <path d="M5 3v4M3 5h4M19 17v4M17 19h4" />
              </svg>
            )}
          </button>
        </div>

        <div className="thumb-upload-row thumb-upload-row--full">
          <input
            type="file"
            accept="image/*"
            className="thumb-file-input"
            onChange={(e) => {
              setNotice(null);
              const f = e.target.files?.[0];
              if (f) onChange(f);
            }}
          />
        </div>
      </div>

      {notice && (
        <div className="thumb-ai-notice" role="status">
          <span>{notice}</span>
          <button type="button" className="secondary sm" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}
