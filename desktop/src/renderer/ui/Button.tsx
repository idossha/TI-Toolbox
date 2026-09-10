import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cn } from "./utils";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "destructive";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Spinner replaces the leading icon; the label and width stay put. */
  loading?: boolean;
  icon?: ReactNode;
}

/** Primary actions read as verbs: "Run simulation", "Queue 3 jobs", "Stop". */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading = false, icon, disabled, className, children, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={rest.type ?? "button"}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "btn",
        `btn-${variant}`,
        size === "sm" && "btn-sm",
        size === "lg" && "btn-lg",
        className,
      )}
      {...rest}
    >
      {loading ? <span className="btn-spinner" aria-hidden /> : icon}
      <span className="btn-label-loading">{children}</span>
    </button>
  );
});

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon: ReactNode;
  /** Required: icon-only buttons must never be unlabelled. */
  "aria-label": string;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { variant = "ghost", size = "md", icon, className, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={rest.type ?? "button"}
      className={cn("btn", "btn-icon", `btn-${variant}`, size === "sm" && "btn-sm", size === "lg" && "btn-lg", className)}
      {...rest}
    >
      {icon}
    </button>
  );
});
