"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV: { label: string; href: string; match?: string; icon: React.ReactNode }[] = [
  {
    label: "Simulations",
    href: "/",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </svg>
    ),
  },
  {
    label: "History",
    href: "/history",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <polyline points="12 6 12 12 16 14" />
      </svg>
    ),
  },
  {
    label: "Manual Upload",
    href: "/submit",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="17 8 12 3 7 8" />
        <line x1="12" y1="3" x2="12" y2="15" />
      </svg>
    ),
  },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  /* Immersive simulation view: no sidebar/header chrome */
  if (pathname && /^\/jobs\/[^/]+\/view$/.test(pathname)) {
    return <>{children}</>;
  }

  const isJobPage = pathname?.startsWith("/jobs/");
  const jobId = isJobPage ? pathname.split("/")[2] : null;
  const isRunPage = pathname?.match(/^\/simulations\/[^/]+\/run/);
  const runSimId = isRunPage ? pathname?.split("/")[2] : null;

  return (
    <div className="app-shell">
      {/* ── Sidebar ── */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="12 2 2 7 12 12 22 7 12 2" />
              <polyline points="2 17 12 22 22 17" />
              <polyline points="2 12 12 17 22 12" />
            </svg>
          </div>
          <div>
            <div className="sidebar-logo-title">OpenFOAM</div>
            <div className="sidebar-logo-sub">Simulation Platform</div>
          </div>
        </div>

        <nav className="sidebar-nav">
          <div className="sidebar-section-label">Main</div>
          {NAV.map((item) => {
            let active = false;
            if (item.href === "/") {
              active = pathname === "/" || !!isRunPage || pathname === "/simulations/new";
            } else {
              active = !!pathname?.startsWith(item.match ?? item.href);
            }
            return (
              <Link key={item.href} href={item.href} className={`sidebar-link${active ? " active" : ""}`}>
                <span className="sidebar-link-icon">{item.icon}</span>
                {item.label}
              </Link>
            );
          })}

          {isJobPage && jobId && (
            <>
              <div className="sidebar-section-label" style={{ marginTop: "1.25rem" }}>Current Job</div>
              <Link href={`/jobs/${jobId}`} className="sidebar-link active">
                <span className="sidebar-link-icon">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                    <line x1="16" y1="13" x2="8" y2="13" />
                    <line x1="16" y1="17" x2="8" y2="17" />
                  </svg>
                </span>
                Visualize
              </Link>
              <div className="sidebar-job-id" title={jobId}>{jobId.slice(0, 8)}…</div>
            </>
          )}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-section-label">System</div>
          <Link href="/settings" className={`sidebar-link${pathname === "/settings" ? " active" : ""}`}>
            <span className="sidebar-link-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </span>
            Settings
          </Link>
          <a
            href="https://www.openfoam.com/documentation/guides/latest/doc/"
            target="_blank"
            rel="noreferrer"
            className="sidebar-link"
          >
            <span className="sidebar-link-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
                <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
              </svg>
            </span>
            Documentation
          </a>

          <div className="sidebar-user">
            <div className="sidebar-user-avatar">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
            </div>
            <div className="sidebar-user-info">
              <div className="sidebar-user-name">Engineer</div>
              <div className="sidebar-user-role">Operator</div>
            </div>
          </div>
        </div>
      </aside>

      {/* ── Main content area ── */}
      <div className="app-main">
        {/* ── Header ── */}
        <header className="app-header">
          <div className="app-header-left">
          <h1 className="app-header-title">
            {isJobPage
              ? "Job"
              : isRunPage
                ? "Run Simulation"
                : pathname === "/history"
                  ? "Run History"
                  : pathname === "/submit"
                    ? "Manual Upload"
                    : pathname === "/settings"
                      ? "Settings"
                      : pathname === "/simulations/new"
                        ? "New Simulation"
                        : "Simulations"}
          </h1>
            {isJobPage && jobId && (
              <span className="app-header-breadcrumb">
                <Link href="/">Simulations</Link>
                <span className="app-header-sep">/</span>
                <Link href={`/jobs/${jobId}`}>{jobId.slice(0, 8)}…</Link>
              </span>
            )}
            {isRunPage && runSimId && (
              <span className="app-header-breadcrumb">
                <Link href="/">Simulations</Link>
                <span className="app-header-sep">/</span>
                <span>Run</span>
              </span>
            )}
            {pathname === "/simulations/new" && (
              <span className="app-header-breadcrumb">
                <Link href="/">Simulations</Link>
                <span className="app-header-sep">/</span>
                <span>New</span>
              </span>
            )}
          </div>
        </header>

        {/* ── Page content ── */}
        <div className="app-content">
          {children}
        </div>
      </div>
    </div>
  );
}
