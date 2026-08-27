import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

type Tone = "neutral" | "success" | "warning" | "danger";

export function Badge({
  className,
  tone = "neutral",
  ...props
}: ComponentProps<"span"> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-medium",
        tone === "neutral" && "border-border bg-muted text-muted-foreground",
        tone === "success" && "border-emerald-400/20 bg-emerald-400/10 text-emerald-300",
        tone === "warning" && "border-amber-400/20 bg-amber-400/10 text-amber-300",
        tone === "danger" && "border-red-400/20 bg-red-400/10 text-red-300",
        className,
      )}
      {...props}
    />
  );
}
