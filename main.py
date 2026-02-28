import os
import urllib.parse
import time
import uuid

import aiohttp

import filetype

from astrbot.api import logger
from astrbot.api import AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Image, BaseMessageComponent, Reply
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
import astrbot.api.message_components as Comp


@register(
    "表情包提取",
    "Yangyuwuhan",
    "把QQ表情包提取为可保存的文件",
    "2.0.0",
    "https://github.com/Yangyuwuhan/astrbot_plugin_meme_grabber",
)
class MemeGrabberPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # 获取配置中的临时文件保存目录
        self.data_dir = self.config.get(
            "temp_dir", "data/plugins/astrbot_plugins_convetpicture"
        )
        os.makedirs(self.data_dir, exist_ok=True)
        # 获取是否在发送后删除临时文件的配置
        self.delete_after_send = self.config.get("delete_after_send", True)
        # 获取默认图片扩展名
        self.default_extension = self.config.get("default_extension", "jpg")
        # 获取图片下载超时时间
        self.download_timeout = self.config.get("download_timeout", 10)

    async def download_image(self, picture_url: str, relative_path: str) -> bool:
        """下载图片到本地

        Args:
            picture_url: 图片URL
            relative_path: 保存路径

        Returns:
            bool: 下载是否成功
        """
        try:
            # 使用 aiohttp 进行异步请求，设置超时时间
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    picture_url, timeout=self.download_timeout
                ) as response:
                    if response.status == 200:
                        content = await response.read()
                        # 保存图片到本地
                        # 确保目录存在
                        os.makedirs(os.path.dirname(relative_path), exist_ok=True)
                        with open(relative_path, "wb") as f:
                            f.write(content)
                        return True
                    else:
                        logger.error(f"下载图片失败，状态码: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"下载图片时发生错误: {str(e)}")
            return False

    async def send_file_to_user(
        self, event: AstrMessageEvent, file_path: str, filename: str
    ):
        """发送文件给用户

        Args:
            event: 消息事件
            file_path: 文件路径
            filename: 文件名
        """
        try:
            # 使用 AstrBot 官方接口发送文件
            chain: list[BaseMessageComponent] = [
                Comp.File(file=file_path, name=filename)
            ]
            yield event.chain_result(chain)
            event.stop_event()
            # 根据配置决定是否删除临时文件
            if self.delete_after_send:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"删除临时文件: {file_path}")
                except Exception as e:
                    logger.error(f"删除临时文件时发生错误: {str(e)}")
        except Exception as e:
            logger.error(f"发送文件时发生错误: {str(e)}")
            yield event.plain_result(f"发送文件失败: {str(e)}")
            event.stop_event()

    async def handle_image_message(self, event: AstrMessageEvent, image_msg: Image):
        """处理图片消息

        Args:
            event: 消息事件
            image_msg: 图片消息
        """
        try:
            assert isinstance(event, AiocqhttpMessageEvent)
            client = event.bot
            picture_id = image_msg.file

            # 调用 QQ 协议获取图片
            response = await client.api.call_action("get_image", file_id=picture_id)
            localdiskpath = response["file"]
            abs_path = os.path.abspath(localdiskpath)

            # 只通过filetype库判断文件格式
            file_extension = f".{self.default_extension}"  # 默认扩展名

            try:
                kind = filetype.guess(abs_path)
                if kind and kind.extension:
                    file_extension = f".{kind.extension}"
            except Exception as e:
                logger.error(f"使用filetype判断图片类型失败: {str(e)}")

            # 生成唯一的文件名
            timestamp = int(time.time() * 1000)
            unique_id = uuid.uuid4().hex[:8]
            filename = f"图片_{timestamp}_{unique_id}{file_extension}"

            logger.info(f"处理图片: {abs_path}, 扩展名: {file_extension}")
            async for result in self.send_file_to_user(event, abs_path, filename):
                yield result
        except Exception as e:
            logger.error(f"处理图片消息时发生错误: {str(e)}")
            yield event.plain_result(f"处理图片失败: {str(e)}")
            event.stop_event()
            event.should_call_llm(False)

    async def handle_reply_message(self, event: AstrMessageEvent, reply_msg: Reply):
        """处理回复消息

        Args:
            event: 消息事件
            reply_msg: 回复消息
        """
        try:
            assert isinstance(event, AiocqhttpMessageEvent)
            client = event.bot

            # 获取回复的原始消息
            response = await client.api.call_action("get_msg", message_id=reply_msg.id)
            reply_msg_content = response["message"]

            for msg in reply_msg_content:
                if msg["type"] == "image":
                    # 提取图片信息
                    picture_url = msg["data"]["url"]
                    logger.info(f"处理回复中的图片: {picture_url}")

                    # 提取图片URL的扩展名，保持原格式
                    parsed_url = urllib.parse.urlparse(picture_url)
                    path = parsed_url.path
                    ext = os.path.splitext(path)[1].lower()
                    if not ext:
                        ext = f".{self.default_extension}"  # 默认格式

                    # 生成唯一的文件名和保存路径
                    timestamp = int(time.time() * 1000)
                    unique_id = uuid.uuid4().hex[:8]
                    filename = f"图片_{timestamp}_{unique_id}{ext}"
                    relative_path = os.path.join(self.data_dir, filename)

                    # 处理官方表情
                    if "/club/item/" in picture_url:
                        result = await self.download_image(picture_url, relative_path)
                        if result:
                            absolute_path = os.path.abspath(relative_path)
                            # 已在上面生成了唯一的文件名
                            async for result in self.send_file_to_user(
                                event, absolute_path, filename
                            ):
                                yield result
                        else:
                            yield event.plain_result("图片下载失败")
                            event.stop_event()
                            event.should_call_llm(False)
                        return

                    # 处理普通图片
                    if (
                        isinstance(msg, dict)
                        and "data" in msg
                        and "file" in msg["data"]
                    ):
                        file_id = msg["data"]["file"]
                        response = await client.api.call_action(
                            "get_image", file_id=file_id
                        )
                        localdiskpath = response["file"]
                        abs_path = os.path.abspath(localdiskpath)

                        # 只通过filetype库判断文件格式
                        file_extension = ".jpg"  # 默认扩展名

                        try:
                            kind = filetype.guess(abs_path)
                            if kind and kind.extension:
                                file_extension = f".{kind.extension}"
                        except Exception as e:
                            logger.error(f"使用filetype判断图片类型失败: {str(e)}")

                        # 生成唯一的文件名
                        timestamp = int(time.time() * 1000)
                        unique_id = uuid.uuid4().hex[:8]
                        filename = f"图片_{timestamp}_{unique_id}{file_extension}"

                        async for result in self.send_file_to_user(
                            event, abs_path, filename
                        ):
                            yield result
                        return
        except Exception as e:
            logger.error(f"处理回复消息时发生错误: {str(e)}")
            yield event.plain_result(f"处理回复失败: {str(e)}")
            event.stop_event()
            event.should_call_llm(False)

    @filter.command("转换")
    async def convert_command(self, event: AstrMessageEvent):
        """转换图片为可保存的文件格式

        用法: 发送图片或回复包含图片的消息，然后输入 /转换 指令
        """
        event.should_call_llm(False)
        message_chain = event.get_messages()

        # 检查平台是否支持
        if event.get_platform_name() != "aiocqhttp":
            yield event.plain_result("抱歉，该功能仅支持 QQ 平台")
            event.stop_event()
            event.should_call_llm(False)
            return

        for msg in message_chain:
            if msg.type == "Image":
                # 类型断言，确保是Image类型
                assert isinstance(msg, Image)
                # 处理图片消息
                async for result in self.handle_image_message(event, msg):
                    yield result
                return
            elif msg.type == "Reply":
                # 类型断言，确保是Reply类型
                assert isinstance(msg, Reply)
                # 处理回复消息
                async for result in self.handle_reply_message(event, msg):
                    yield result
                return

        # 没有找到图片
        yield event.plain_result("请引用表情包或在对话中包含表情包")
        event.stop_event()
        event.should_call_llm(False)

    async def terminate(self):
        """插件终止时的清理操作"""
        # 清理可能遗留的临时图片文件
        try:
            if os.path.exists(self.data_dir):
                for file in os.listdir(self.data_dir):
                    file_path = os.path.join(self.data_dir, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        logger.info(f"清理临时文件: {file_path}")
        except Exception as e:
            logger.error(f"清理临时文件时发生错误: {str(e)}")
