"use client";

// Inline error for a failed Analytics_API request (Req 17.15, 17.16). It says what
// went wrong and how to fix it, in Park LU's voice and without apologizing, and
// offers Try Again. A warning icon and a title carry the state, never color alone.
import type { ReactNode } from "react";
import { ApiRequestError, ApiUnreachableError } from "../lib/api";
import { API_START_COMMAND } from "../lib/format";
import { Icon } from "./Icons";
import styles from "./ApiError.module.css";

export interface ApiErrorProps {
  /** The caught error: ApiUnreachableError, ApiRequestError, or anything else. */
  error: unknown;
  /** Shows a Try Again button that calls this. Without it, the copy says to reload the page. */
  onRetry?: () => void;
  /** Title-style heading that overrides the default, e.g. "Zones Didn't Load". */
  title?: string;
  /** Heading level for the title. Default 2. */
  headingLevel?: 2 | 3;
  className?: string;
}

interface ErrorCopy {
  title: string;
  /** What went wrong. */
  message: ReactNode;
  /** How to fix it; null when the message already says. */
  fix: string | null;
  /** Raw detail for unexpected errors, shown small. */
  detail?: string;
}

// Duck-typed fallbacks keep detection working if Fast Refresh reloads lib/api.ts
// and the class identity changes.
function isUnreachable(error: unknown): error is ApiUnreachableError {
  return (
    error instanceof ApiUnreachableError ||
    (error instanceof Error && error.name === "ApiUnreachableError" && "apiBase" in error)
  );
}

function isRequestError(error: unknown): error is ApiRequestError {
  return (
    error instanceof ApiRequestError ||
    (error instanceof Error && error.name === "ApiRequestError" && "status" in error)
  );
}

/** "destination" → "Destination", "game_day" → "Game Day". */
function titleCase(id: string): string {
  return id
    .split("_")
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}

function describe(error: unknown, canRetry: boolean): ErrorCopy {
  // Without a Try Again button: reloading helps when the API was down, but would
  // discard the input that a parameter error asks people to change.
  const retry = canRetry ? "select Try Again" : "reload this page";
  const resubmit = canRetry ? "select Try Again" : "try again";

  if (isUnreachable(error)) {
    return {
      title: "Can't Reach the Park LU API",
      message: (
        <>
          Park LU can&apos;t reach its API at {error.apiBase}. Start it from the api folder with{" "}
          <code className={styles.code}>{API_START_COMMAND}</code>, then {retry}.
        </>
      ),
      fix: null,
    };
  }

  if (isRequestError(error)) {
    const param = error.parameter;
    const message = error.message || `The Park LU API rejected the request (HTTP ${error.status}).`;

    if (error.status >= 500) {
      return {
        title: "Park LU API Error",
        message,
        fix: `Check the API terminal for details, then ${retry}.`,
      };
    }

    switch (error.error) {
      case "missing_parameter":
        return {
          title: "Missing Information",
          message,
          fix: param
            ? `Provide a ${param} value, then ${resubmit}.`
            : `Provide the missing value, then ${resubmit}.`,
        };
      case "invalid_parameter":
        return {
          title: "Value Not Accepted",
          message,
          fix: param ? `Change the ${param} value, then ${resubmit}.` : `Change the request, then ${resubmit}.`,
        };
      case "not_found":
        return {
          title: param ? `${titleCase(param)} Not Found` : "Not Found",
          message,
          fix: "Reload this page to refresh the list, then choose again.",
        };
      case "unknown_scenario":
        return {
          title: "Unknown Scenario",
          message,
          fix: error.allowed?.length
            ? `Choose one of these scenarios: ${error.allowed.map(titleCase).join(", ")}.`
            : "Choose Game Day, Family Weekend, or Reset.",
        };
      case "http_error":
      case "invalid_response":
        // lib/api.ts already wrote the fix into these messages.
        return { title: "Request Didn't Complete", message, fix: null };
      default:
        return { title: "Request Didn't Complete", message, fix: `Check the request, then ${resubmit}.` };
    }
  }

  return {
    title: "Request Didn't Complete",
    message: "Park LU couldn't complete this request.",
    fix: `Check that the API is running, then ${retry}.`,
    detail: error instanceof Error && error.message ? error.message : undefined,
  };
}

export function ApiError({ error, onRetry, title, headingLevel = 2, className }: ApiErrorProps) {
  const copy = describe(error, Boolean(onRetry));
  const Heading = headingLevel === 3 ? "h3" : "h2";

  return (
    <div role="alert" className={["card", styles.root, className].filter(Boolean).join(" ")}>
      <Icon name="warning" className={styles.icon} />
      <div className={styles.body}>
        <Heading className={styles.title}>{title ?? copy.title}</Heading>
        <p className={styles.message}>{copy.message}</p>
        {copy.fix ? <p className={styles.fix}>{copy.fix}</p> : null}
        {copy.detail ? <p className={styles.detail}>Details: {copy.detail}</p> : null}
        {onRetry ? (
          <button type="button" className={`button ${styles.retry}`} onClick={onRetry}>
            <Icon name="refresh" size={20} />
            Try Again
          </button>
        ) : null}
      </div>
    </div>
  );
}
