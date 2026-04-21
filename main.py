def main() -> None:
    print(
        "Smart Office Life Agent\n"
        "실행 방법:\n"
        "  uv run python -m src.main --mode desktop --user-id 1\n"
        "  uv run python -m src.main --mode web --user-id 1\n"
        "  uv run python -m src.main --mode scheduler\n"
        "  uv run python -m src.main --mode seed\n"
    )


if __name__ == "__main__":
    main()
