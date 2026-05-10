from __future__ import annotations

from ai_automate_contro.plans.artifacts import list_output_artifacts


class OutputCommandsMixin:
    def do_output(self, _: str) -> None:
        """Show the last run output directory."""
        output_dir = self._resolve_latest_output_dir()
        if output_dir is None:
            self.poutput("output: <none>")
            return
        self.poutput(str(output_dir))

    def do_report(self, _: str) -> None:
        """Show the latest run report.md."""
        output_dir = self._resolve_latest_output_dir()
        if output_dir is None:
            self.poutput("report: <none>")
            return
        report_path = output_dir / "report.md"
        if not report_path.exists():
            self.poutput(f"report not found: {report_path}")
            return
        self.poutput(report_path.read_text(encoding="utf-8", errors="replace"))

    def do_logs(self, arg: str) -> None:
        """Show recent run log lines: logs [lines]"""
        try:
            line_count = int(arg.strip()) if arg.strip() else 80
        except ValueError:
            self.perror("usage: logs [lines]")
            return
        if line_count <= 0:
            self.perror("lines must be greater than 0")
            return

        output_dir = self._resolve_latest_output_dir()
        if output_dir is None:
            self.poutput("log: <none>")
            return
        log_path = output_dir / "run.log"
        if not log_path.exists():
            self.poutput(f"log not found: {log_path}")
            return
        lines = log_path.read_text(encoding="utf-8").splitlines()
        for line in lines[-line_count:]:
            self.poutput(line)

    def do_events(self, arg: str) -> None:
        """Show recent structured event lines: events [lines]"""
        try:
            line_count = int(arg.strip()) if arg.strip() else 40
        except ValueError:
            self.perror("usage: events [lines]")
            return
        if line_count <= 0:
            self.perror("lines must be greater than 0")
            return

        output_dir = self._resolve_latest_output_dir()
        if output_dir is None:
            self.poutput("events: <none>")
            return
        events_path = output_dir / "events.jsonl"
        if not events_path.exists():
            self.poutput(f"events not found: {events_path}")
            return
        lines = events_path.read_text(encoding="utf-8").splitlines()
        for line in lines[-line_count:]:
            self.poutput(line)

    def do_artifacts(self, arg: str) -> None:
        """List output artifacts: artifacts [filter] [limit]"""
        parts = arg.split()
        filter_text = ""
        limit = 80
        if len(parts) == 1:
            if parts[0].isdigit():
                limit = int(parts[0])
            else:
                filter_text = parts[0]
        elif len(parts) == 2:
            filter_text = parts[0]
            try:
                limit = int(parts[1])
            except ValueError:
                self.perror("usage: artifacts [filter] [limit]")
                return
        elif len(parts) > 2:
            self.perror("usage: artifacts [filter] [limit]")
            return
        if limit <= 0:
            self.perror("limit must be greater than 0")
            return
        try:
            plan_path = self._require_current_plan()
        except ValueError as error:
            self.perror(str(error))
            return
        artifacts = list_output_artifacts(plan_path, filter_text=filter_text, limit=limit)
        if not artifacts:
            self.poutput("artifacts: <none>")
            return
        for artifact in artifacts:
            self.poutput(f"{artifact.relative_path} | {artifact.size} bytes")
