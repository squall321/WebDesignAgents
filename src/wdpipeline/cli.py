# wda CLI — 파이프라인 P0~P5 실행 진입점 (typer)
from __future__ import annotations

import typer

app = typer.Typer(help="WebDesignAgents 파이프라인 CLI")


@app.command()
def version() -> None:
    """설치 확인용."""
    typer.echo("webdesignagents 0.1.0")


if __name__ == "__main__":
    app()
