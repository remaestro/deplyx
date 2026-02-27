from typing import Any

import httpx


class SlackNotifier:
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    async def send(self, title: str, body: str, metadata: dict[str, Any] | None = None) -> bool:
        text = f"*{title}*\n{body}"
        if metadata:
            details = "\n".join(f"• {k}: {v}" for k, v in metadata.items())
            text = f"{text}\n{details}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(self.webhook_url, json={"text": text})
            return 200 <= response.status_code < 300
