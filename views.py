import asyncio

import discord

from api_client import (
    APIClientError,
    list_models
)

from database import (
    save_api_config,
    save_model
)

from config import (
    MAX_MODELS_IN_SELECT
)


class APISetupModal(
    discord.ui.Modal,
    title="設定 API"
):

    api_url = discord.ui.TextInput(
        label="API URL",
        placeholder="https://example.com/v1",
        required=True,
        max_length=500
    )

    api_key = discord.ui.TextInput(
        label="API Key",
        placeholder="貼上你的 API Key",
        required=True,
        max_length=1000,
        style=discord.TextStyle.paragraph
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        await interaction.response.defer(
            ephemeral=True,
            thinking=True
        )

        try:

            api_url = str(
                self.api_url
            ).strip()

            api_key = str(
                self.api_key
            ).strip()

            models = await asyncio.to_thread(
                list_models,
                api_url,
                api_key
            )

            save_api_config(
                interaction.user.id,
                api_url,
                api_key,
                None
            )

            await interaction.edit_original_response(
                content="API 設定成功，請從下面選擇模型。",
                view=ModelSelectView(
                    interaction.user.id,
                    api_url,
                    api_key,
                    models
                )
            )

        except APIClientError as e:

            await interaction.edit_original_response(
                content=f"API 設定失敗：{e}"
            )

        except Exception as e:

            print(
                f"API 設定未知錯誤：{e}"
            )

            await interaction.edit_original_response(
                content="API 設定失敗：系統發生未知錯誤，請稍後再試。"
            )


class ManualModelModal(
    discord.ui.Modal,
    title="自行輸入模型"
):

    model = discord.ui.TextInput(
        label="模型名稱",
        placeholder="例如：gemini-3.8-flash",
        required=True,
        max_length=200
    )

    def __init__(
        self,
        user_id
    ):

        super().__init__()

        self.user_id = user_id

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        if interaction.user.id != self.user_id:

            await interaction.response.send_message(
                "這個模型設定不是你的。",
                ephemeral=True
            )

            return

        model_name = str(
            self.model
        ).strip()

        if not model_name:

            await interaction.response.send_message(
                "模型名稱不可為空。",
                ephemeral=True
            )

            return

        try:

            save_model(
                self.user_id,
                model_name
            )

            await interaction.response.send_message(
                f"模型設定成功：{model_name}",
                ephemeral=True
            )

        except Exception as e:

            print(
                f"手動模型儲存失敗：{e}"
            )

            await interaction.response.send_message(
                "模型設定失敗：無法儲存設定，請稍後再試。",
                ephemeral=True
            )


class ManualModelButton(
    discord.ui.Button
):

    def __init__(
        self,
        user_id
    ):

        super().__init__(
            label="自行輸入模型",
            style=discord.ButtonStyle.secondary
        )

        self.user_id = user_id

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        if interaction.user.id != self.user_id:

            await interaction.response.send_message(
                "這個模型設定不是你的。",
                ephemeral=True
            )

            return

        await interaction.response.send_modal(
            ManualModelModal(
                self.user_id
            )
        )


class ModelSelect(
    discord.ui.Select
):

    def __init__(
        self,
        user_id,
        models
    ):

        options = [
            discord.SelectOption(
                label=model[:100],
                value=model[:100]
            )
            for model in models[
                :MAX_MODELS_IN_SELECT
            ]
        ]

        super().__init__(
            placeholder="從模型清單選擇",
            min_values=1,
            max_values=1,
            options=options
        )

        self.user_id = user_id

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        if interaction.user.id != self.user_id:

            await interaction.response.send_message(
                "這個模型選單不是你的。",
                ephemeral=True
            )

            return

        selected_model = self.values[0]

        try:

            save_model(
                self.user_id,
                selected_model
            )

            await interaction.response.edit_message(
                content=(
                    f"模型設定成功："
                    f"{selected_model}"
                ),
                view=None
            )

        except Exception as e:

            print(
                f"模型儲存失敗：{e}"
            )

            await interaction.response.send_message(
                "模型設定失敗：無法儲存設定，請稍後再試。",
                ephemeral=True
            )


class ModelSelectView(
    discord.ui.View
):

    def __init__(
        self,
        user_id,
        api_url,
        api_key,
        models
    ):

        super().__init__(
            timeout=120
        )

        self.user_id = user_id
        self.api_url = api_url
        self.api_key = api_key
        self.models = models

        if models:

            self.add_item(
                ModelSelect(
                    user_id,
                    models
                )
            )

        self.add_item(
            ManualModelButton(
                user_id
            )
        )
           