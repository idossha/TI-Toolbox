import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "../ui/Button";
import { Callout } from "../ui/Feedback";
import { Stack } from "../ui/Layout";

type Props = { children: ReactNode; pageId: string };
type State = { error: Error | null };

/**
 * Catches render errors of one screen so a single bad cell never blanks the whole app
 * (TODO.md §2.9 "renderer error boundary"). Retained with its page: navigation cannot discard
 * an error the user still needs to read; "Try again" rebuilds that screen explicitly.
 */
export class PageErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`[tit] screen "${this.props.pageId}" failed to render`, error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div style={{ padding: 24, maxWidth: 720 }}>
        <Stack gap={12}>
          <Callout kind="danger" title="This screen hit an error">
            <p>{this.state.error.message || String(this.state.error)}</p>
            <p>The rest of the app keeps working. Try again, or reload if it happens twice.</p>
          </Callout>
          <div style={{ display: "flex", gap: 8 }}>
            <Button variant="primary" onClick={() => this.setState({ error: null })}>
              Try again
            </Button>
            <Button variant="secondary" onClick={() => window.location.reload()}>
              Reload app
            </Button>
          </div>
        </Stack>
      </div>
    );
  }
}
