import {
  CircleAlert,
  CircleCheck,
  CircleDashed,
  CircleX,
  Inbox,
  LoaderCircle,
  type LucideIcon
} from "lucide-react";
import {
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type ReactNode
} from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

export function Button({
  variant = "secondary",
  busy = false,
  icon: Icon,
  children,
  className = "",
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  busy?: boolean;
  icon?: LucideIcon;
}) {
  return (
    <button
      className={`ui-button ui-button-${variant} ${className}`.trim()}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...props}
    >
      {busy ? (
        <span className="ui-icon-spin" aria-hidden="true"><LoaderCircle size={16} /></span>
      ) : Icon ? (
        <Icon size={16} aria-hidden="true" />
      ) : null}
      <span>{children}</span>
    </button>
  );
}

const STATUS_ICONS: Record<string, LucideIcon> = {
  approved: CircleCheck,
  completed: CircleCheck,
  ready: CircleCheck,
  failed: CircleX,
  rejected: CircleX,
  error: CircleX,
  proposed: CircleDashed,
  previewing: LoaderCircle,
  processing: LoaderCircle,
  loading: LoaderCircle,
  stale: CircleAlert
};

export function StatusBadge({
  status,
  children,
  className = ""
}: {
  status: string;
  children: ReactNode;
  className?: string;
}) {
  const Icon = STATUS_ICONS[status] ?? CircleDashed;
  const spinning = ["previewing", "processing", "loading"].includes(status);
  return (
    <span
      className={`status-badge ${className}`.trim()}
      data-status={status}
      role="status"
    >
      <span className={spinning ? "ui-icon-spin" : "ui-icon"} aria-hidden="true">
        <Icon size={12} />
      </span>
      {children}
    </span>
  );
}

export function EmptyState({
  title,
  description,
  action
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <section className="empty-state panel" data-ui-state="empty">
      <Inbox size={24} aria-hidden="true" />
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </section>
  );
}

export function SkeletonCards({
  count = 3,
  ...props
}: HTMLAttributes<HTMLDivElement> & { count?: number }) {
  return (
    <div
      className="clip-grid skeleton-grid"
      data-ui-state="loading"
      aria-busy="true"
      {...props}
    >
      {Array.from({ length: count }, (_, index) => (
        <span key={index} aria-hidden="true" />
      ))}
    </div>
  );
}
