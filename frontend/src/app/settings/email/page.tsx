import { PlaceholderPage } from "@/components/placeholder-page";

export default function EmailSettingsPage() {
  return (
    <PlaceholderPage
      eyebrow="Daily digest"
      title="Email"
      path="/settings/email"
      description="Configure the private top-10 digest destination and inspect delivery status without adding mail behavior yet."
      nextStep="SMTP secrets, digest scheduling, retries, and EmailDelivery persistence remain intentionally out of scope."
    />
  );
}
