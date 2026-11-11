import Link from "next/link";
import { featureGuide } from "@/lib/feature-guide";

type RouteHeaderProps = {
  eyebrow: string;
  title: string;
  description: string;
  path: string;
};

export function RouteHeader({ title, description, path }: RouteHeaderProps) {
  const guides = featureGuide.filter((feature) => feature.route === path);
  return (
    <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border pb-4">
      <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      <details className="max-w-lg text-sm text-muted-foreground">
        <summary className="cursor-pointer py-2 text-right underline underline-offset-4">
          Help
        </summary>
        <p className="mt-3 leading-6">{description}</p>
        {guides.map((feature) => (
          <Link
            key={feature.id}
            href={`/tutorial#${feature.id}`}
            className="mt-2 block underline"
          >
            {feature.title}
          </Link>
        ))}
      </details>
    </header>
  );
}
