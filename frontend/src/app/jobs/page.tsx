import { PlaceholderPage } from "@/components/placeholder-page";

export default function JobsPage() {
  return (
    <PlaceholderPage
      eyebrow="Canonical catalog"
      title="Jobs"
      path="/jobs"
      description="Browse the durable job records created after observations from approved sources are normalized and deduplicated."
      nextStep="The canonical-job table, filters, labels, and batch context will be implemented after persistence is connected."
    />
  );
}
