import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";
import {
  AlertCircle,
  ArrowUpRight,
  Check,
  ChevronRight,
  LoaderCircle,
  X,
} from "lucide-react";

export function IconButton({
  label,
  children,
  onClick,
  active = false,
}: {
  label: string;
  children: ReactNode;
  onClick: () => void;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      className={`icon-button${active ? " active" : ""}`}
      title={label}
      aria-label={label}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
export function Badge({
  status,
  children,
}: {
  status?: string;
  children?: ReactNode;
}) {
  const value = status ?? "";
  const tone = /accepted|published|complete|succeeded|verified|known/.test(
    value,
  )
    ? "success"
    : /block|fail|error/.test(value)
      ? "danger"
      : /review|draft|candidate|decision|warn/.test(value)
        ? "warning"
        : "neutral";
  return (
    <span className={`badge ${tone}`}>
      <span />
      {children ?? value.replaceAll("_", " ")}
    </span>
  );
}
export function ErrorNotice({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="notice error" role="alert">
      <AlertCircle size={17} />
      <div>
        {message}
        {onRetry && (
          <button onClick={onRetry} className="text-button">
            Try again <ChevronRight size={13} />
          </button>
        )}
      </div>
    </div>
  );
}
export function EmptyState({
  icon,
  title,
  text,
  action,
}: {
  icon: ReactNode;
  title: string;
  text: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">{icon}</span>
      <h2>{title}</h2>
      <p>{text}</p>
      {action}
    </div>
  );
}
export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <span className="loading-inline" role="status">
      <LoaderCircle className="spin" size={17} />
      {label}
    </span>
  );
}
export function Modal({
  title,
  eyebrow,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  eyebrow?: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const returnFocus = useRef<Element | null>(null);
  useEffect(() => {
    returnFocus.current = document.activeElement;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusable = () => [
      ...(ref.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex="0"]',
      ) ?? []),
    ];
    (
      focusable().find((el) => el.tagName === "INPUT") ?? focusable()[0]
    )?.focus();
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") {
        const items = focusable();
        const first = items[0];
        const last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener("keydown", handler);
      if (returnFocus.current instanceof HTMLElement)
        returnFocus.current.focus();
    };
  }, [onClose]);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`modal${wide ? " wide" : ""}`}
      >
        <header className="modal-head">
          <div>
            {eyebrow && <span className="eyebrow">{eyebrow}</span>}
            <h2 id={titleId}>{title}</h2>
          </div>
          <IconButton label="Close dialog" onClick={onClose}>
            <X size={20} />
          </IconButton>
        </header>
        {children}
      </div>
    </div>
  );
}
export function KeyValue({
  label,
  children,
  mono,
}: {
  label: string;
  children: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="key-value">
      <dt>{label}</dt>
      <dd className={mono ? "mono" : ""}>{children}</dd>
    </div>
  );
}
export function ExternalLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <a className="text-button" href={href} download>
      {children}
      <ArrowUpRight size={14} />
    </a>
  );
}
export function CheckLine({ children }: { children: ReactNode }) {
  return (
    <div className="check-line">
      <Check size={15} />
      {children}
    </div>
  );
}
export const pretty = (value: unknown) =>
  typeof value === "string" ? value : JSON.stringify(value, null, 2);
export const human = (value: string) =>
  value.replaceAll("_", " ").replaceAll(".", " · ");
export const shortDate = (value?: string) =>
  value
    ? new Intl.DateTimeFormat("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
      }).format(new Date(value))
    : "—";
export const money = (value: string | number | null) =>
  value === null
    ? "—"
    : new Intl.NumberFormat("en-IE", {
        style: "currency",
        currency: "EUR",
        maximumFractionDigits: 2,
      }).format(Number(value));
export const number = (value: string | number | null, ratio = false) =>
  value === null
    ? "—"
    : new Intl.NumberFormat(
        "en-GB",
        ratio
          ? {
              style: "percent",
              maximumFractionDigits: 1,
              signDisplay: "exceptZero",
            }
          : { maximumFractionDigits: 2, signDisplay: "exceptZero" },
      ).format(Number(value));
