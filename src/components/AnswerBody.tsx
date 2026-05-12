import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

/**
 * Renders a Hermes answer string with light markdown + citation rewriting.
 *
 * Supported markdown (line-level):
 *   - `### Header` / `## Header` → h3 / h2
 *   - `1. text`, `2. text` → ordered list
 *   - `- text`, `* text` → bulleted list
 *   - blank line → paragraph break
 *
 * Supported inline tokens:
 *   - `**bold**`
 *   - `[card]` (no id) — gray inline badge, non-clickable
 *   - `[card:<id>]` — anchor link to `#card-<id>` (in-page; same meeting)
 *   - `[cards:<id>, <id>, ...]` — plural form, one link per id
 *   - `[seg:<id>]` — clickable button → onSegClick(id) (for in-meeting Ask)
 *   - `[project:<ws>:meeting:<m>:card:<c>]` — Link to `/ws/<ws>/meetings/<m>#card-<c>`
 *   - `[project:<ws>:meeting:<m>:seg:<s>]` — Link to `/ws/<ws>/meetings/<m>#seg-<s>`
 *
 * `onSegClick` is optional. When omitted (e.g. workspace-level Ask page where
 * segment ids alone aren't meaningful), `[seg:<id>]` falls back to a plain
 * gray badge.
 */
export function AnswerBody({
  text,
  onSegClick,
}: {
  text: string;
  onSegClick?: (segId: string) => void;
}) {
  const lines = text.split('\n');

  type Span =
    | { kind: 'text'; value: string }
    | { kind: 'bold'; value: string }
    | { kind: 'cardEmpty' }
    | { kind: 'card'; id: string }
    | { kind: 'seg'; id: string }
    | { kind: 'projCard'; ws: string; meetingId: string; cardId: string }
    | { kind: 'projSeg'; ws: string; meetingId: string; segId: string };

  const tokenRe =
    /\*\*([^*]+)\*\*|\[project:([^:\]]+):meeting:([^:\]]+):card:([^\]]+)\]|\[project:([^:\]]+):meeting:([^:\]]+):seg:([^\]]+)\]|\[cards?:([^\]]+)\]|\[card\]|\[seg:([^\]]+)\]/g;

  function parseInline(line: string): Span[] {
    const spans: Span[] = [];
    let cursor = 0;
    let m: RegExpExecArray | null;
    tokenRe.lastIndex = 0;
    while ((m = tokenRe.exec(line)) !== null) {
      if (m.index > cursor) {
        spans.push({ kind: 'text', value: line.slice(cursor, m.index) });
      }
      if (m[1] !== undefined) {
        spans.push({ kind: 'bold', value: m[1] });
      } else if (m[2] !== undefined) {
        spans.push({ kind: 'projCard', ws: m[2], meetingId: m[3], cardId: m[4] });
      } else if (m[5] !== undefined) {
        spans.push({ kind: 'projSeg', ws: m[5], meetingId: m[6], segId: m[7] });
      } else if (m[8] !== undefined) {
        // [card:<id>] or [cards:<id>, <id>, ...]
        const ids = m[8]
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean);
        ids.forEach((id, i) => {
          if (i > 0) spans.push({ kind: 'text', value: ', ' });
          spans.push({ kind: 'card', id });
        });
      } else if (m[9] !== undefined) {
        spans.push({ kind: 'seg', id: m[9] });
      } else {
        // matched `[card]` literal with no id
        spans.push({ kind: 'cardEmpty' });
      }
      cursor = m.index + m[0].length;
    }
    if (cursor < line.length) {
      spans.push({ kind: 'text', value: line.slice(cursor) });
    }
    return spans;
  }

  function renderSpans(spans: Span[], keyPrefix: string): ReactNode {
    return spans.map((s, i) => {
      const key = `${keyPrefix}-${i}`;
      if (s.kind === 'text') return <span key={key}>{s.value}</span>;
      if (s.kind === 'bold') return <strong key={key}>{s.value}</strong>;
      if (s.kind === 'cardEmpty') {
        return (
          <span
            key={key}
            className="rounded bg-gray-100 px-1 text-xs italic text-gray-500"
            title="Citation marker (no id)"
          >
            [card]
          </span>
        );
      }
      if (s.kind === 'card') {
        return (
          <a
            key={key}
            href={`#card-${s.id}`}
            className="rounded bg-indigo-50 px-1 text-xs text-indigo-700 hover:underline"
            title={`Memory card ${s.id}`}
          >
            [card]
          </a>
        );
      }
      if (s.kind === 'projCard') {
        return (
          <Link
            key={key}
            to={`/ws/${s.ws}/meetings/${s.meetingId}#card-${s.cardId}`}
            className="rounded bg-indigo-50 px-1 text-xs text-indigo-700 hover:underline"
            title={`Card ${s.cardId} in meeting ${s.meetingId} (workspace ${s.ws})`}
          >
            [card]
          </Link>
        );
      }
      if (s.kind === 'projSeg') {
        return (
          <Link
            key={key}
            to={`/ws/${s.ws}/meetings/${s.meetingId}#seg-${s.segId}`}
            className="rounded bg-gray-100 px-1 text-xs text-gray-600 hover:bg-gray-200"
            title={`Segment ${s.segId} in meeting ${s.meetingId} (workspace ${s.ws})`}
          >
            [src]
          </Link>
        );
      }
      // seg
      if (onSegClick) {
        return (
          <button
            key={key}
            type="button"
            onClick={() => onSegClick(s.id)}
            className="rounded bg-gray-100 px-1 text-xs text-gray-600 hover:bg-gray-200"
            title={`Segment ${s.id}`}
          >
            [src]
          </button>
        );
      }
      return (
        <span
          key={key}
          className="rounded bg-gray-100 px-1 text-xs text-gray-600"
          title={`Segment ${s.id}`}
        >
          [src]
        </span>
      );
    });
  }

  const elements: ReactNode[] = [];
  let listType: 'ul' | 'ol' | null = null;
  let listBuf: string[] = [];

  function flushList(keyPrefix: string) {
    if (listBuf.length === 0) return;
    const Tag = listType === 'ol' ? 'ol' : 'ul';
    const className =
      listType === 'ol' ? 'ml-5 list-decimal space-y-0.5' : 'ml-4 list-disc space-y-0.5';
    elements.push(
      <Tag key={`${keyPrefix}-list`} className={className}>
        {listBuf.map((item, bi) => (
          <li key={bi}>{renderSpans(parseInline(item), `${keyPrefix}-li${bi}`)}</li>
        ))}
      </Tag>,
    );
    listBuf = [];
    listType = null;
  }

  lines.forEach((line, li) => {
    const trimmed = line.trim();
    // Numbered list item: "1. text"
    const olMatch = /^(\d+)\.\s+(.+)$/.exec(trimmed);
    if (olMatch) {
      if (listType === 'ul') flushList(`l${li}`);
      listType = 'ol';
      listBuf.push(olMatch[2]);
      return;
    }
    // Bulleted list item
    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      if (listType === 'ol') flushList(`l${li}`);
      listType = 'ul';
      listBuf.push(trimmed.slice(2));
      return;
    }
    flushList(`l${li}`);
    if (trimmed.length === 0) return;
    // Headers
    if (trimmed.startsWith('### ')) {
      elements.push(
        <h3 key={`l${li}`} className="mt-2 text-sm font-semibold text-gray-900">
          {renderSpans(parseInline(trimmed.slice(4)), `l${li}`)}
        </h3>,
      );
      return;
    }
    if (trimmed.startsWith('## ')) {
      elements.push(
        <h2 key={`l${li}`} className="mt-2 text-base font-semibold text-gray-900">
          {renderSpans(parseInline(trimmed.slice(3)), `l${li}`)}
        </h2>,
      );
      return;
    }
    elements.push(
      <p key={`l${li}`} className="leading-relaxed">
        {renderSpans(parseInline(trimmed), `l${li}`)}
      </p>,
    );
  });
  flushList('end');

  return <div className="space-y-1 text-sm text-gray-800">{elements}</div>;
}
