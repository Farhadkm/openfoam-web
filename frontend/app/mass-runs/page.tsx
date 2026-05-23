import { redirect } from "next/navigation";

export default function MassRunsPage() {
  redirect("/history?tab=mass");
}
