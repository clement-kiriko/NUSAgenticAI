from dotenv import load_dotenv

from runtime.mcp_server import run_stdio_server


def main() -> None:
    load_dotenv(override=True)
    run_stdio_server()


if __name__ == "__main__":
    main()
