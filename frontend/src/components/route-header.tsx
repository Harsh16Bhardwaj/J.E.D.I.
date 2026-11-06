import Link from "next/link";
import { Badge } from "@/components/ui/badge";
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
    <header className="max-w-4xl">
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <Badge className="rounded-full border border-acid/30 bg-acid/10 px-3 font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-acid">
          {eyebrow}
        </Badge>
        <code className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
          {path}
        </code>
      </div>
      <h1 className="max-w-4xl text-4xl font-semibold leading-[0.96] tracking-[-0.05em] sm:text-6xl">
        {title}
      </h1>
      <p className="mt-5 max-w-2xl text-base leading-7 text-muted-foreground sm:text-lg">
        {description}
      </p>
      {guides.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2">
          {guides.map((feature) => (
            <Link key={feature.id} href={`/tutorial#${feature.id}`} className="text-sm text-muted-foreground underline hover:text-foreground">
              Guide for {feature.title}
            </Link>
          ))}
        </div>
      )}
    </header>
  );
}
