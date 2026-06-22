import React from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  children: React.ReactNode;
  fallbackTitle?: string;
}

interface State {
  hasError: boolean;
  errorMessage: string;
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, errorMessage: "" };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, errorMessage: error.message };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[ErrorBoundary] Uncaught render error:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-full items-center justify-center p-8">
          <div className="flex flex-col items-center gap-4 rounded-lg border border-border bg-card p-8 text-center max-w-sm w-full shadow-lg">
            <AlertTriangle className="h-10 w-10 text-destructive" aria-hidden="true" />
            <div>
              <p className="font-semibold text-sm">
                {this.props.fallbackTitle ?? "Something went wrong"}
              </p>
              {this.state.errorMessage && (
                <p className="mt-2 text-xs text-muted-foreground font-mono break-all">
                  {this.state.errorMessage}
                </p>
              )}
            </div>
            <Button
              size="sm"
              onClick={() => window.location.reload()}
            >
              Reload app
            </Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
