import { PlaceholderPage } from "@/components/placeholder-page";

export default function ProfileSettingsPage() {
  return (
    <PlaceholderPage
      eyebrow="Versioned input"
      title="Resume + preferences"
      path="/settings/profile"
      description="Maintain the structured candidate profile and resume text used by semantic suitability and future preference learning."
      nextStep="Profile uploads and activation will create immutable ProfileVersion records in a later phase."
    />
  );
}
