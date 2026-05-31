import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-[var(--foreground)] text-[var(--background)]",
        secondary: "border-[var(--border)] bg-[var(--surface-2)] text-[var(--muted-foreground)]",
        success: "border-[#7bc3ae] bg-[#e4f6ef] text-[#14532d]",
        warning: "border-[#f1cf8a] bg-[#fff5df] text-[#7b4d07]",
        destructive: "border-[#f2b0b6] bg-[#fff0f2] text-[#991b1b]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

function Badge({ className, variant, ...props }: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
