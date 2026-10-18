// Empty state: says what the view has nothing to show and offers the next action
// (Req 17.17), e.g. "No spaces opening in the next 15 minutes" with Plan a Visit.
// Use title-style capitalization for the title and the action label (Req 17.14).
//
// No "use client", so a server page can render it with an href action. An onClick
// action needs a client parent, because functions can't cross into the client.
import Link from "next/link";
import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icons";
import styles from "./EmptyState.module.css";

export type EmptyStateAction =
  | { label: string; href: string; onClick?: never }
  | { label: string; onClick: () => void; href?: never };

export interface EmptyStateProps {
  /** Title-style, e.g. "No Sessions Match These Selections". */
  title: string;
  /** One or two sentences describing the situation. Inline content only. */
  description: ReactNode;
  /** Next step: a link (`href`) or a button (`onClick`). Title-style label, e.g. "Plan a Visit". */
  action?: EmptyStateAction;
  /** Optional decorative icon above the title. */
  icon?: IconName;
  /** Heading level for the title. Default 2. */
  headingLevel?: 2 | 3;
  className?: string;
}

export function EmptyState({
  title,
  description,
  action,
  icon,
  headingLevel = 2,
  className,
}: EmptyStateProps) {
  const Heading = headingLevel === 3 ? "h3" : "h2";

  return (
    <div className={[styles.root, className].filter(Boolean).join(" ")}>
      {icon ? <Icon name={icon} size={32} className={styles.icon} /> : null}
      <Heading className={styles.title}>{title}</Heading>
      <p className={styles.description}>{description}</p>
      {action ? (
        action.href !== undefined ? (
          <Link href={action.href} className={`button ${styles.action}`}>
            {action.label}
          </Link>
        ) : (
          <button type="button" className={`button ${styles.action}`} onClick={action.onClick}>
            {action.label}
          </button>
        )
      ) : null}
    </div>
  );
}
