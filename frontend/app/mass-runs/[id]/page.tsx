import { redirect } from "next/navigation";

type Props = { params: Promise<{ id: string }> };

export default async function MassRunDetailPage({ params }: Props) {
  const { id } = await params;
  redirect(`/history?tab=mass&id=${encodeURIComponent(id)}`);
}
