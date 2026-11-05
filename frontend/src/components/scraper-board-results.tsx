import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ScrapeRunStats } from "@/lib/api";

export function ScraperBoardResults({ stats }: { stats: ScrapeRunStats }) {
  return (
    <section aria-labelledby="board-results" className="mt-4 border-t border-border pt-4">
      <h3 id="board-results" className="ops-label text-purple">Results by employer board</h3>
      <p className="mt-2 text-xs text-muted-foreground">
        Jobs seen counts postings returned by each board. Unique candidates count
        staged postings after deduplication within this run.
      </p>
      {stats.importedJobs !== null && (
        <p className="mt-2 text-sm font-bold">{stats.importedJobs} jobs in the imported batch</p>
      )}
      {stats.byBoard.length ? (
        <div className="mt-3 max-h-96 overflow-auto rounded-lg border border-border">
          <Table aria-labelledby="board-results">
            <TableHeader>
              <TableRow>
                {["Board", "Outcome", "Seen", "Unique", "Importable", "Selected", "Direct requests", "Bright Data units"].map((label) => (
                  <TableHead key={label}>{label}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {stats.byBoard.map((board) => (
                <TableRow key={board.sourceKey}>
                  <TableCell>
                    <p className="font-bold">{board.name}</p>
                    <p className="text-xs text-muted-foreground">{board.atsType} · {board.sourceKey}</p>
                  </TableCell>
                  <TableCell>
                    {board.status === "PENDING" && board.retryAt
                      ? `Retry eligible at ${new Date(board.retryAt).toLocaleTimeString()}`
                      : board.status === "SUCCEEDED" && board.jobsSeen === 0
                        ? "No openings returned"
                        : board.status}
                    {board.errorMessage && <p className="max-w-64 whitespace-normal break-words text-xs text-coral">{board.errorMessage}</p>}
                    {board.retryCount > 0 && <p className="text-xs text-muted-foreground">{board.retryCount} automatic retries queued or used</p>}
                  </TableCell>
                  <TableCell>{board.jobsSeen}</TableCell>
                  <TableCell>{board.uniqueCandidates}</TableCell>
                  <TableCell>{board.importable}</TableCell>
                  <TableCell>{board.selected}</TableCell>
                  <TableCell>{board.directRequests}</TableCell>
                  <TableCell>{board.brightDataUsed}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground">This run has no boards queued.</p>
      )}
    </section>
  );
}
