import type { Metadata } from "next";
import "./globals.css";
import Shell from "./components/Shell";

export const metadata: Metadata = {
  title: "Forge",
  description: "Submit and monitor CFD simulations",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const uiBuild =
    process.env.NEXT_PUBLIC_FORGE_UI_BUILD_REV?.trim() || "local-dev";
  return (
    <html lang="en" data-forge-ui-build={uiBuild}>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
