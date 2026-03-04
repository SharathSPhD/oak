import { cn } from "@/lib/utils";

type Variant = "default" | "success" | "warning" | "danger" | "info" | "secondary";

const variantClasses: Record<Variant, string> = {
  default: "bg-slate-100 text-slate-700",
  success: "bg-emerald-100 text-emerald-800",
  warning: "bg-amber-100 text-amber-800",
  danger: "bg-red-100 text-red-800",
  info: "bg-sky-100 text-sky-800",
  secondary: "bg-slate-50 text-slate-500",
};

export function Badge({
  variant = "default",
  className,
  children,
}: {
  variant?: Variant;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        variantClasses[variant],
        className
      )}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { variant: Variant; label: string }> = {
    pending: { variant: "secondary", label: "Pending" },
    assembling: { variant: "info", label: "Assembling" },
    active: { variant: "warning", label: "Active" },
    complete: { variant: "success", label: "Complete" },
    failed: { variant: "danger", label: "Failed" },
    claimed: { variant: "info", label: "Claimed" },
    running: { variant: "success", label: "Running" },
    idle: { variant: "secondary", label: "Idle" },
    terminated: { variant: "danger", label: "Terminated" },
    probationary: { variant: "warning", label: "Probationary" },
    permanent: { variant: "success", label: "Permanent" },
  };
  const { variant, label } = map[status] ?? { variant: "default" as Variant, label: status };
  return <Badge variant={variant}>{label}</Badge>;
}
