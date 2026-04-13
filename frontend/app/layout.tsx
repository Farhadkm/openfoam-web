import type { Metadata } from "next";
import "./globals.css";
import Shell from "./components/Shell";

export const metadata: Metadata = {
  title: "OpenFOAM Web",
  description: "Submit and monitor OpenFOAM simulations",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const uiBuild =
    process.env.NEXT_PUBLIC_OPENFOAM_UI_BUILD_REV?.trim() || "local-dev";
  return (
    <html lang="en" data-openfoam-ui-build={uiBuild}>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
