import { PlaceholderPage } from "@/components/placeholder-page";

export default async function JobDetailPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;

  return (
    <PlaceholderPage
      eyebrow="Job detail"
      title={`Job ${jobId}`}
      path={`/jobs/${jobId}`}
      description="Review the complete description, source observations, model signals, fit reasons, relevance label, and application state."
      nextStep="This route will join CanonicalJob, JobPrediction, JobState, and JobEvent data without asking the ML model to invent explanations."
    />
  );
}
