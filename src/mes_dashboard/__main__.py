"""Development entry point for MES Dashboard."""

from mes_dashboard.app import create_app


def main() -> None:
    app = create_app()
    app.run(debug=True, use_reloader=True, host="0.0.0.0", port=8080)


if __name__ == '__main__':
    main()
