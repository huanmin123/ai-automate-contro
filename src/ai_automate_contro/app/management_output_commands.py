from __future__ import annotations

from ai_automate_contro.plans.artifacts import list_output_artifacts


class OutputCommandsMixin:
    def do_output(self, _: str) -> None:
        """查看最近运行输出目录。"""
        output_dir = self._resolve_latest_output_dir()
        if output_dir is None:
            self.poutput("输出目录：<无>")
            return
        self.poutput(str(output_dir))

    def do_report(self, _: str) -> None:
        """查看最近运行的 report.md。"""
        output_dir = self._resolve_latest_output_dir()
        if output_dir is None:
            self.poutput("报告：<无>")
            return
        report_path = output_dir / "report.md"
        if not report_path.exists():
            self.poutput(f"未找到报告：{report_path}")
            return
        self.poutput(report_path.read_text(encoding="utf-8", errors="replace"))

    def do_logs(self, arg: str) -> None:
        """查看最近运行日志：logs [lines]"""
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
            self.poutput("日志：<无>")
            return
        log_path = output_dir / "run.log"
        if not log_path.exists():
            self.poutput(f"未找到日志：{log_path}")
            return
        lines = log_path.read_text(encoding="utf-8").splitlines()
        for line in lines[-line_count:]:
            self.poutput(line)

    def do_events(self, arg: str) -> None:
        """查看最近结构化事件：events [lines]"""
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
            self.poutput("事件：<无>")
            return
        events_path = output_dir / "events.jsonl"
        if not events_path.exists():
            self.poutput(f"未找到事件文件：{events_path}")
            return
        lines = events_path.read_text(encoding="utf-8").splitlines()
        for line in lines[-line_count:]:
            self.poutput(line)

    def do_artifacts(self, arg: str) -> None:
        """列出输出产物：artifacts [filter] [limit]"""
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
            self.perror(error)
            return
        artifacts = list_output_artifacts(plan_path, filter_text=filter_text, limit=limit)
        if not artifacts:
            self.poutput("输出产物：<无>")
            return
        for artifact in artifacts:
            self.poutput(f"{artifact.relative_path} | {artifact.size} 字节")
