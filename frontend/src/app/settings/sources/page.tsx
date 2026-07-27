import { PlaceholderPage } from "@/components/placeholder-page";

export default function SourceSettingsPage() {
  return (
    <PlaceholderPage
      eyebrow="Approved manifest"
      title="Sources"
      path="/settings/sources"
      description="Define exactly where the upstream automation may find jobs, including allowed domains, enablement, and priority."
      nextStep="SourceDefinition CRUD and envelope validation against allowed domains will be wired after the database migration."
    />
  );
}
