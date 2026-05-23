"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { MassRunDetailPanel } from "@/app/components/mass-run/MassRunDetailPanel";
import { MassRunsHistoryContent } from "@/app/components/history/MassRunsHistoryContent";
import { SingleHistoryContent } from "@/app/components/history/SingleHistoryContent";

type HistoryTab = "single" | "mass";

function parseTab(value: string | null): HistoryTab {
  return value === "mass" ? "mass" : "single";
}

function tabHref(next: HistoryTab): string {
  return next === "mass" ? "/history?tab=mass" : "/history?tab=single";
}

function HistoryPageContent() {
  const searchParams = useSearchParams();
  const tab = parseTab(searchParams.get("tab"));
  const massRunId = searchParams.get("id");

  return (
    <>
      <div className="page-tabs" role="tablist" aria-label="History type">
        <Link
          href={tabHref("single")}
          scroll={false}
          replace
          role="tab"
          aria-selected={tab === "single"}
          className={`page-tab${tab === "single" ? " active" : ""}`}
        >
          Single
        </Link>
        <Link
          href={tabHref("mass")}
          scroll={false}
          replace
          role="tab"
          aria-selected={tab === "mass"}
          className={`page-tab${tab === "mass" ? " active" : ""}`}
        >
          Mass
        </Link>
      </div>

      {tab === "single" ? (
        <SingleHistoryContent />
      ) : massRunId ? (
        <>
          <div className="page-desc row gap-sm" style={{ flexWrap: "wrap", alignItems: "center" }}>
            <Link href="/history?tab=mass" className="btn secondary sm">
              ← Mass runs
            </Link>
            <Link href="/mass-run" className="btn secondary sm">
              New mass run
            </Link>
          </div>
          <MassRunDetailPanel
            massRunId={massRunId}
            showNewRunLink
            listHref="/history?tab=mass"
          />
        </>
      ) : (
        <MassRunsHistoryContent />
      )}
    </>
  );
}

export default function HistoryPage() {
  return (
    <Suspense fallback={<p style={{ color: "var(--muted)", margin: 0, fontSize: 13 }}>Loading…</p>}>
      <HistoryPageContent />
    </Suspense>
  );
}
