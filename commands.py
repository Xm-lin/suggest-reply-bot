import asyncio

import discord

from discord import app_commands

from api_client import (
    APIClientError,
    list_models
)

from database import (
    get_api_config,
    save_model
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


async def get_conversation_for_user(
    channel,
    target_message,
    user_id,
    limit=10
):

    messages = []

    try:

        async for message in channel.history(
            before=target_message,
            limit=limit
        ):

            if not message.content.strip():
                continue

            if message.author.id == user_id:

                speaker = "我"

            elif (
                message.author.id
                == target_message.author.id
            ):

                speaker = "對方"

            else:

                speaker = "其他人"

            messages.append(
                f"{speaker}：{message.content}"
            )

    except discord.Forbidden:

        raise RuntimeError(
            "無法讀取聊天紀錄，請確認 Bot 有查看頻道與讀取訊息的權限。"
        )

    except discord.HTTPException:

        raise RuntimeError(
            "聊天紀錄讀取失敗，請稍後再試。"
        )

    messages.reverse()

    messages.append(
        f"對方：{target_message.content}"
    )

    conversation_text = "\n".join(
        messages
    )

    user_reply_count = sum(
        1
        for message in messages
        if message.startswith("我：")
    )

    return (
        conversation_text,
        user_reply_count >= 2
    )


def register_commands(bot):

    @bot.tree.command(
        name="set_api",
        description="設定你的 API URL 與 API Key"
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

            (
                conversation_text,
                has_user_history
            ) = await get_conversation_for_user(
                interaction.channel,
                message,
                interaction.user.id,
                limit=10
            )

            status, replies = await asyncio.to_thread(
                analyze_and_generate,
                config["api_url"],
                config["api_key"],
                config["model"],
                conversation_text,
                message.content,
                has_user_history
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

        except RuntimeError as e:

            await interaction.edit_original_response(
                content=f"聊天紀錄失敗：{e}"
            )

        except Exception as e:

            print(
                f"建議回覆未知錯誤：{e}"
            )

            await interaction.edit_original_response(
                content="建議回覆失敗：系統發生未知錯誤，請稍後再試。"
            )