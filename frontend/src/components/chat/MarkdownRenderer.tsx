import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { Components } from "react-markdown";

interface MarkdownRendererProps {
  content: string;
}

const components: Components = {
  code({ className, children, ...props }) {
    const match = /language-(\w+)/.exec(className ?? "");
    const isBlock = Boolean(match);
    const codeString = String(children).replace(/\n$/, "");

    if (!isBlock) {
      return (
        <code
          className="rounded bg-muted px-1 py-0.5 font-mono text-xs text-foreground"
          {...props}
        >
          {children}
        </code>
      );
    }

    return (
      <SyntaxHighlighter
        style={vscDarkPlus}
        language={match![1]}
        PreTag="div"
        className="!rounded-md !text-xs !my-2 !border !border-border"
        wrapLongLines
      >
        {codeString}
      </SyntaxHighlighter>
    );
  },

  a({ href, children }) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary underline underline-offset-4 hover:text-primary/80 break-words"
      >
        {children}
      </a>
    );
  },

  table({ children }) {
    return (
      <div className="my-2 overflow-x-auto rounded-md border border-border">
        <table className="min-w-full text-xs">{children}</table>
      </div>
    );
  },

  thead({ children }) {
    return <thead className="bg-muted">{children}</thead>;
  },

  th({ children }) {
    return (
      <th className="border-b border-border px-3 py-2 text-left font-medium text-muted-foreground whitespace-nowrap">
        {children}
      </th>
    );
  },

  td({ children }) {
    return (
      <td className="border-b border-border/40 px-3 py-2">{children}</td>
    );
  },

  ul({ children }) {
    return <ul className="my-2 ml-4 list-disc space-y-1">{children}</ul>;
  },

  ol({ children }) {
    return <ol className="my-2 ml-4 list-decimal space-y-1">{children}</ol>;
  },

  li({ children }) {
    return <li className="text-sm leading-relaxed">{children}</li>;
  },

  p({ children }) {
    return <p className="mb-2 last:mb-0 leading-relaxed text-sm">{children}</p>;
  },

  blockquote({ children }) {
    return (
      <blockquote className="my-2 border-l-2 border-primary pl-3 text-muted-foreground italic text-sm">
        {children}
      </blockquote>
    );
  },

  h1({ children }) {
    return <h1 className="text-base font-semibold mt-3 mb-1">{children}</h1>;
  },

  h2({ children }) {
    return <h2 className="text-sm font-semibold mt-3 mb-1">{children}</h2>;
  },

  h3({ children }) {
    return <h3 className="text-sm font-medium mt-2 mb-1">{children}</h3>;
  },

  hr() {
    return <hr className="my-3 border-border" />;
  },
};

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {content}
    </ReactMarkdown>
  );
}
