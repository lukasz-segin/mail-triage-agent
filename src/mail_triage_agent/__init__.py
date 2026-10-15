import logging

import uvicorn


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s"
    )
    uvicorn.run("mail_triage_agent.app:app", host="0.0.0.0", port=8000)
