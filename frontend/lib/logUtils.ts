/** Lines that often indicate failure (last matches surfaced for AI debug). */
const FATAL_LINE_RE =
  /FOAM FATAL|Fatal Error|fatal error|--> FOAM|Error in function|failed\b|Segmentation fault|Aborted|cannot find|No such file|bad exit/i;

export function extractFatalLogHints(log: string, maxLines = 12): string[] {
  if (!log.trim()) return [];
  const lines = log.split("\n");
  const hits: string[] = [];
  for (const line of lines) {
    const t = line.trimEnd();
    if (!t || !FATAL_LINE_RE.test(t)) continue;
    hits.push(t);
  }
  if (hits.length === 0) {
    const tail = lines.filter((l) => l.trim()).slice(-8);
    return tail;
  }
  return hits.slice(-maxLines);
}
