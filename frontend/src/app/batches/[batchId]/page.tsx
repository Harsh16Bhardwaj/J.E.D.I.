import { PlaceholderPage } from "@/components/placeholder-page";

export default async function BatchDetailPage({
  params,
}: {
  params: Promise<{ batchId: string }>;
}) {
  const { batchId } = await params;

  return (
    <PlaceholderPage
      eyebrow="Batch detail"
      title={`Batch ${batchId}`}
      path={`/batches/${batchId}`}
      description="One import’s counts, stage history, duplicate decisions, predictions, and digest delivery will converge here."
      nextStep="This route will read ImportBatch, JobObservation, ProcessingRun, JobPrediction, and EmailDelivery records."
    />
  );
}
