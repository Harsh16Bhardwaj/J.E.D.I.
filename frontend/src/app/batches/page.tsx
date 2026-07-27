import { PlaceholderPage } from "@/components/placeholder-page";

export default function BatchesPage() {
  return (
    <PlaceholderPage
      eyebrow="Imports"
      title="Batch control"
      path="/batches"
      description="Inspect every manually uploaded JSON envelope and its path through validation, normalization, deduplication, scoring, and digest delivery."
      nextStep="The import form, validation report, and processing controls will be added with database CRUD."
    />
  );
}
