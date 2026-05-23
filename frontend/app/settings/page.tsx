"use client";

import { useEffect, useState } from "react";
import { ForgeSelect } from "@/app/components/ui/ForgeSelect";

const FONT_SIZES = [
  { value: "12", label: "Small (12px)" },
  { value: "14", label: "Default (14px)" },
  { value: "16", label: "Large (16px)" },
  { value: "18", label: "Extra Large (18px)" },
];

const LANGUAGES = [
  { value: "en", label: "English" },
];

function loadSettings() {
  if (typeof window === "undefined") return { fontSize: "14", language: "en" };
  try {
    const raw = localStorage.getItem("forge_settings");
    if (raw) return JSON.parse(raw) as { fontSize: string; language: string };
  } catch { /* ignore */ }
  return { fontSize: "14", language: "en" };
}

function saveSettings(s: { fontSize: string; language: string }) {
  localStorage.setItem("forge_settings", JSON.stringify(s));
}

function applyFontSize(size: string) {
  document.documentElement.style.fontSize = `${size}px`;
}

export default function SettingsPage() {
  const [fontSize, setFontSize] = useState("14");
  const [language, setLanguage] = useState("en");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const s = loadSettings();
    setFontSize(s.fontSize);
    setLanguage(s.language);
    applyFontSize(s.fontSize);
  }, []);

  const handleSave = () => {
    const s = { fontSize, language };
    saveSettings(s);
    applyFontSize(fontSize);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleReset = () => {
    setFontSize("14");
    setLanguage("en");
    saveSettings({ fontSize: "14", language: "en" });
    applyFontSize("14");
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <>
      <div className="page-desc">
        Configure application preferences. Changes are stored locally in your browser.
      </div>

      <section className="panel" style={{ maxWidth: 560 }}>
        <div className="panel-header">
          <div className="section-title" style={{ margin: 0 }}>Appearance</div>
        </div>

        <div className="settings-group">
          <label htmlFor="font-size">Font Size</label>
          <ForgeSelect
            id="font-size"
            value={fontSize}
            onChange={(v) => {
              setFontSize(v);
              applyFontSize(v);
            }}
            options={FONT_SIZES}
            aria-label="Font size"
          />
          <small className="hint">Adjusts the base font size across the application.</small>
        </div>

        <div className="settings-group" style={{ marginTop: 20 }}>
          <label htmlFor="language">Language</label>
          <ForgeSelect
            id="language"
            value={language}
            onChange={setLanguage}
            options={LANGUAGES}
            aria-label="Language"
          />
          <small className="hint">More languages will be available in future updates.</small>
        </div>

        <div className="row gap-sm" style={{ marginTop: 24 }}>
          <button type="button" onClick={handleSave}>
            Save Settings
          </button>
          <button type="button" className="secondary" onClick={handleReset}>
            Reset to Defaults
          </button>
          {saved && (
            <span style={{ fontSize: 12, color: "var(--ok)", alignSelf: "center" }}>
              Settings saved
            </span>
          )}
        </div>
      </section>
    </>
  );
}
