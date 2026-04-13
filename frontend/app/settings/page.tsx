"use client";

import { useEffect, useState } from "react";

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
    const raw = localStorage.getItem("openfoam_settings");
    if (raw) return JSON.parse(raw) as { fontSize: string; language: string };
  } catch { /* ignore */ }
  return { fontSize: "14", language: "en" };
}

function saveSettings(s: { fontSize: string; language: string }) {
  localStorage.setItem("openfoam_settings", JSON.stringify(s));
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
          <select
            id="font-size"
            value={fontSize}
            onChange={(e) => {
              setFontSize(e.target.value);
              applyFontSize(e.target.value);
            }}
          >
            {FONT_SIZES.map((f) => (
              <option key={f.value} value={f.value}>{f.label}</option>
            ))}
          </select>
          <small className="hint">Adjusts the base font size across the application.</small>
        </div>

        <div className="settings-group" style={{ marginTop: 20 }}>
          <label htmlFor="language">Language</label>
          <select id="language" value={language} onChange={(e) => setLanguage(e.target.value)}>
            {LANGUAGES.map((l) => (
              <option key={l.value} value={l.value}>{l.label}</option>
            ))}
          </select>
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
