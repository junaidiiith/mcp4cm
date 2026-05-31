import * as React from "react";
import { cn } from "@/lib/utils";

function Label({ className, ...props }: React.ComponentProps<"label">) {
  return (
    <label
      data-slot="label"
      className={cn("grid gap-1 text-sm font-semibold text-[var(--foreground)]", className)}
      {...props}
    />
  );
}

export { Label };
