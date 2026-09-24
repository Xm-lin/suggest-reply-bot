import threading

from http.server import (
    HTTPServer,
    SimpleHTTPRequestHandler
)

import discord

from discord.ext import commands

from config import (
    PORT,
    DISCORD_TOKEN
)

from database import (
    init_db
)

from commands import (
    register_commands
)


class HealthHandler(
    SimpleHTTPRequestHandler
):

    def do_GET(self):

        self.send_response(200)

        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8"
        )

        self.end_headers()

        self.wfile.write(
            b"OK"
        )

    def log_message(
        self,
        format,
        *args
    ):

        return


def run_dummy_server():

    try:

        server = HTTPServer(
            (
                "0.0.0.0",
                PORT
            ),
            HealthHandler
        )

        print(
            f"Dummy server running on port {PORT}"
        )

        server.serve_forever()

    except Exception as e:

        print(
            f"Dummy server 啟動失敗：{e}"
        )


class SuggestReplyBot(
    commands.Bot
):

    def __init__(self):

        intents = discord.Intents.default()

        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,

            # 同時允許：
            # 1. 安裝到伺服器
            # 2. 安裝到使用者帳號
            allowed_installs=discord.app_commands.AppInstallationType(
                guild=True,
                user=True
            ),

            # 允許 Application Commands
            # 出現在伺服器、DM、私人頻道
            allowed_contexts=discord.app_commands.AppCommandContext(
                guild=True,
                dm_channel=True,
                private_channel=True
            )
        )

    async def setup_hook(self):

        register_commands(
            self
        )

        await self.tree.sync()

        print(
            "Slash commands synced"
        )

    async def on_ready(self):

        print(
            f"Bot 已登入：{self.user}"
        )


def main():

    init_db()

    if not DISCORD_TOKEN:

        raise RuntimeError(
            "找不到 DISCORD_BOT_TOKEN"
        )

    threading.Thread(
        target=run_dummy_server,
        daemon=True
    ).start()

    bot = SuggestReplyBot()

    bot.run(
        DISCORD_TOKEN
    )


if __name__ == "__main__":
    main()