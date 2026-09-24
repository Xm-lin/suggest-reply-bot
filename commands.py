import asyncio

import discord

from discord import app_commands

from api_client import (
    APIClientError,
    list_models
)

from database import (
    get_api_config
)

from reply_generator import (
    analyze_and_generate,
    format_final_result
)

from views import (
    APISetupModal
)


def user_config_error(config):

    if not config:

        return (
            "你還沒有設定 API，"
            "請先使用 /set_api。"
        )

    if (
        not config.get("api_url")
        or not config.get("api_key")
    ):

        return (
            "API 設定不完整，"
            "請重新使用 /set_api。"
        )

    if not config.get("model"):

        return (
            "你還沒有選擇模型，"
            "請先使用 /set_model。"
        )

    return None


def register_commands(bot):

    @bot.tree.command(
        name="set_api",
        description="設定你的 API URL 與 API Key"
    )
    @app_commands.allowed_installs(
        guilds=True,
        users=True
    )
    @app_commands.allowed_contexts(
        guilds=True,
        dms=True,
        private_channels=True
    )
    async def set_api(
        interaction: discord.Interaction
    ):

        await interaction.response.send_modal(
            APISetupModal()
        )


    @bot.tree.command(
        name="set_model",
        description="重新取得並選擇模型"
    )
    @app_commands.allowed_installs(
        guilds=True,
        users=True
    )
    @app_commands.allowed_contexts(
        guilds=True,
        dms=True,
        private_channels=True
    )
    async def set_model(
        interaction: discord.Interaction
    ):

        config = get_api_config(
            interaction.user.id
        )

        if not config:

            await interaction.response.send_message(
                "你還沒有設定 API，請先使用 /set_api。",
                ephemeral=True
            )

            return

        await interaction.response.defer(
            ephemeral=True,
            thinking=True
        )

        try:

            models = await asyncio.to_thread(
                list_models,
                config["api_url"],
                config["api_key"]
            )

            from views import (
                ModelSelectView
            )

            await interaction.edit_original_response(
                content="請選擇模型。",
                view=ModelSelectView(
                    interaction.user.id,
                    config["api_url"],
                    config["api_key"],
                    models
                )
            )

        except APIClientError as e:

            await interaction.edit_original_response(
                content=f"取得模型失敗：{e}"
            )

        except Exception as e:

            print(
                f"/set_model 未知錯誤：{e}"
            )

            await interaction.edit_original_response(
                content="取得模型失敗：系統發生未知錯誤，請稍後再試。"
            )


    @bot.tree.command(
        name="reply",
        description="分析訊息並產生建議回覆"
    )
    @app_commands.allowed_installs(
        guilds=True,
        users=True
    )
    @app_commands.allowed_contexts(
        guilds=True,
        dms=True,
        private_channels=True
    )
    @app_commands.describe(
        message="對方傳給你的訊息"
    )
    async def reply_command(
        interaction: discord.Interaction,
        message: str
    ):

        config = get_api_config(
            interaction.user.id
        )

        error = user_config_error(
            config
        )

        if error:

            await interaction.response.send_message(
                error,
                ephemeral=True
            )

            return

        await interaction.response.defer(
            ephemeral=True,
            thinking=True
        )

        try:

            status, replies = await asyncio.to_thread(
                analyze_and_generate,
                config["api_url"],
                config["api_key"],
                config["model"],
                f"對方：{message}",
                message,
                False
            )

            await interaction.edit_original_response(
                content=format_final_result(
                    status,
                    replies
                )
            )

        except APIClientError as e:

            await interaction.edit_original_response(
                content=f"模型使用失敗：{e}"
            )

        except Exception as e:

            print(
                f"/reply 未知錯誤：{e}"
            )

            await interaction.edit_original_response(
                content="模型使用失敗：系統發生未知錯誤，請稍後再試。"
            )


    @app_commands.context_menu(
        name="建議回覆"
    )
    @app_commands.allowed_installs(
        guilds=True,
        users=True
    )
    @app_commands.allowed_contexts(
        guilds=True,
        dms=True,
        private_channels=True
    )
    async def suggest_reply(
        interaction: discord.Interaction,
        message: discord.Message
    ):

        config = get_api_config(
            interaction.user.id
        )

        error = user_config_error(
            config
        )

        if error:

            await interaction.response.send_message(
                error,
                ephemeral=True
            )

            return

        await interaction.response.defer(
            ephemeral=True,
            thinking=True
        )

        try:

            message_content = message.content.strip()

            if not message_content:

                await interaction.edit_original_response(
                    content="這則訊息沒有可分析的文字內容。"
                )

                return

            conversation_text = (
                f"對方：{message_content}"
            )

            status, replies = await asyncio.to_thread(
                analyze_and_generate,
                config["api_url"],
                config["api_key"],
                config["model"],
                conversation_text,
                message_content,
                False
            )

            await interaction.edit_original_response(
                content=format_final_result(
                    status,
                    replies
                )
            )

        except APIClientError as e:

            await interaction.edit_original_response(
                content=f"模型使用失敗：{e}"
            )

        except Exception as e:

            print(
                f"建議回覆未知錯誤：{e}"
            )

            await interaction.edit_original_response(
                content="建議回覆失敗：系統發生未知錯誤，請稍後再試。"
            )