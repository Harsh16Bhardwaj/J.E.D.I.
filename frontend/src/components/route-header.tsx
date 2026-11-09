import Link from "next/link";
import { featureGuide } from "@/lib/feature-guide";

type RouteHeaderProps = {
  eyebrow: string;
  title: string;
  description: string;
  path: string;
};

export function RouteHeader({
  eyebrow,
  title,
  description,
  path,
}: RouteHeaderProps) {
  const guides = featureGuide.filter((feature) => feature.route === path);
  return (
    <header className="route-heading max-w-4xl">
      <p className="route-eyebrow">
        <i aria-hidden="true" />
        {eyebrow}
      </p>
      <h1 className="mt-5 max-w-4xl text-4xl font-medium leading-[1.04] tracking-[-0.05em] sm:text-5xl">
        {title}
      </h1>
      <p className="mt-4 max-w-2xl text-sm leading-7 text-muted-foreground sm:text-base">
        {description}
      </p>
      {guides.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-x-4 gap-y-2">
          {guides.map((feature) => (
            <Link
              key={feature.id}
              href={`/tutorial#${feature.id}`}
              className="route-guide-link"
            >
              {feature.title} guide &rarr;
            </Link>
          ))}
        </div>
      )}
    </header>
  );
}
