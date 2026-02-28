import os
import urllib.parse
import time
import uuid
import datetime
import shutil

import aiohttp

import filetype

from astrbot.api import logger
from astrbot.api import AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.core.message.components import Image, BaseMessageComponent, Reply
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
import astrbot.api.message_components as Comp


class MemeGrabberPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # 获取插件数据目录（使用框架规范方法）
        self.data_dir = self.config.get("temp_dir", StarTools.get_data_dir(self.name))
        # 转换为绝对路径，确保是字符串类型
        self.data_dir = os.path.abspath(str(self.data_dir))
        os.makedirs(self.data_dir, exist_ok=True)
        # 获取是否在发送后删除临时文件的配置
        self.delete_after_send = self.config.get("delete_after_send", True)
        # 获取默认图片扩展名
        self.default_extension = self.config.get("default_extension", "jpg")
        # 获取图片下载超时时间
        self.download_timeout = self.config.get("download_timeout", 60)
        # 延迟初始化 aiohttp ClientSession，首次使用时创建
        self.session = None

    async def _get_session(self):
        """获取或创建 aiohttp ClientSession

        Returns:
            aiohttp.ClientSession: 异步HTTP会话
        """
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def download_image(self, picture_url: str, relative_path: str) -> bool:
        """下载图片到本地

        Args:
            picture_url: 图片URL
            relative_path: 保存路径

        Returns:
            bool: 下载是否成功
        """
        try:
            # 安全校验：确保只允许 http/https 协议
            parsed_url = urllib.parse.urlparse(picture_url)
            if parsed_url.scheme not in ("http", "https"):
                logger.error(f"不支持的URL协议: {parsed_url.scheme}")
                return False

            # 获取或创建 ClientSession
            session = await self._get_session()
            # 使用复用的 ClientSession 进行异步请求，设置超时时间
            async with session.get(
                picture_url, timeout=self.download_timeout
            ) as response:
                if response.status == 200:
                    # 流式下载，设置最大文件大小为 10MB
                    max_size = 10 * 1024 * 1024
                    current_size = 0
                    # 确保目录存在
                    os.makedirs(os.path.dirname(relative_path), exist_ok=True)
                    with open(relative_path, "wb") as f:
                        async for chunk in response.content:
                            current_size += len(chunk)
                            if current_size > max_size:
                                logger.error("图片文件过大，超过10MB")
                                # 清理已下载的部分文件
                                if os.path.exists(relative_path):
                                    os.remove(relative_path)
                                    logger.info(
                                        f"已清理过大的临时文件: {relative_path}"
                                    )
                                return False
                            f.write(chunk)
                    return True
                else:
                    logger.error(f"下载图片失败，状态码: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"下载图片时发生错误: {str(e)}")
            # 清理可能的临时文件
            if os.path.exists(relative_path):
                os.remove(relative_path)
                logger.info(f"已清理失败的临时文件: {relative_path}")
            return False

    async def send_file_to_user(
        self,
        event: AstrMessageEvent,
        file_path: str,
        filename: str,
        is_plugin_created: bool = True,
    ):
        """发送文件给用户

        Args:
            event: 消息事件
            file_path: 文件路径
            filename: 文件名
            is_plugin_created: 是否为插件创建的文件（用于控制删除行为）
        """
        try:
            # 使用 AstrBot 官方接口发送文件
            chain: list[BaseMessageComponent] = [
                Comp.File(file=file_path, name=filename)
            ]
            # 使用 yield 发送，保持生成器函数特性
            yield event.chain_result(chain)
        except Exception as e:
            logger.error(f"发送文件时发生错误: {str(e)}")
            yield event.plain_result(f"发送文件失败: {str(e)}")
        finally:
            # 根据配置决定是否删除临时文件，仅删除插件自己创建的文件
            if self.delete_after_send and is_plugin_created:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"删除临时文件: {file_path}")
                except Exception as e:
                    logger.error(f"删除临时文件时发生错误: {str(e)}")
            event.stop_event()

    def _generate_filename(self, ext: str) -> str:
        """生成唯一的文件名

        Args:
            ext: 文件扩展名，包含点号

        Returns:
            str: 生成的文件名
        """
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        timestamp = int(time.time() * 1000)
        unique_id = uuid.uuid4().hex[:8]
        return f"meme_{date_str}_{timestamp}_{unique_id}{ext}"

    async def _process_local_image(self, event: AstrMessageEvent, localdiskpath: str):
        """处理本地图片路径，转换为可发送文件

        Args:
            event: 消息事件
            localdiskpath: 本地图片路径

        Yields:
            处理结果
        """
        try:
            temp_abs_path = os.path.abspath(localdiskpath)

            # 只通过filetype库判断文件格式
            file_extension = f".{self.default_extension}"  # 默认扩展名

            try:
                kind = filetype.guess(temp_abs_path)
                if kind and kind.extension:
                    file_extension = f".{kind.extension}"
            except Exception as e:
                logger.error(f"使用filetype判断图片类型失败: {str(e)}")

            # 生成唯一的文件名
            filename = self._generate_filename(file_extension)

            # 复制图片到我们的临时目录
            temp_path = os.path.join(self.data_dir, filename)

            try:
                shutil.copy2(localdiskpath, temp_path)
                abs_path = os.path.abspath(temp_path)
                logger.info(f"图片已复制到临时目录: {abs_path}")
                # 发送插件创建的文件，允许删除
                async for result in self.send_file_to_user(
                    event, abs_path, filename, is_plugin_created=True
                ):
                    yield result
            except Exception as e:
                logger.error(f"复制图片到临时目录失败: {str(e)}")
                abs_path = temp_abs_path
                # 发送原始文件，不允许删除
                async for result in self.send_file_to_user(
                    event, abs_path, filename, is_plugin_created=False
                ):
                    yield result
        except Exception as e:
            logger.error(f"处理本地图片时发生错误: {str(e)}")
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
            if not isinstance(event, AiocqhttpMessageEvent):
                yield event.plain_result("抱歉，该功能仅支持 QQ 平台")
                event.stop_event()
                event.should_call_llm(False)
                return

            client = event.bot

            # 获取回复的原始消息
            response = await client.api.call_action("get_msg", message_id=reply_msg.id)
            reply_msg_content = response["message"]

            found_images = []
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
                    filename = self._generate_filename(ext)
                    relative_path = os.path.join(self.data_dir, filename)

                    # 处理官方表情
                    if "/club/item/" in picture_url:
                        result = await self.download_image(picture_url, relative_path)
                        if result:
                            absolute_path = os.path.abspath(relative_path)
                            found_images.append((absolute_path, filename))
                    # 处理普通图片
                    elif (
                        isinstance(msg, dict)
                        and "data" in msg
                        and "file" in msg["data"]
                    ):
                        file_id = msg["data"]["file"]
                        img_response = await client.api.call_action(
                            "get_image", file_id=file_id
                        )
                        localdiskpath = img_response["file"]

                        # 只通过filetype库判断文件格式
                        file_extension = f".{self.default_extension}"  # 默认扩展名
                        try:
                            kind = filetype.guess(localdiskpath)
                            if kind and kind.extension:
                                file_extension = f".{kind.extension}"
                        except Exception as e:
                            logger.error(f"使用filetype判断图片类型失败: {str(e)}")

                        # 生成唯一的文件名
                        filename = self._generate_filename(file_extension)

                        # 复制图片到我们的临时目录
                        import shutil

                        temp_path = os.path.join(self.data_dir, filename)
                        try:
                            shutil.copy2(localdiskpath, temp_path)
                            abs_path = os.path.abspath(temp_path)
                            logger.info(f"图片已复制到临时目录: {abs_path}")
                            found_images.append((abs_path, filename))
                        except Exception as e:
                            logger.error(f"复制图片到临时目录失败: {str(e)}")
                            # 如果复制失败，使用原始路径
                            abs_path = os.path.abspath(localdiskpath)
                            found_images.append((abs_path, filename))

            # 回复消息中未找到图片
            if not found_images:
                yield event.plain_result("引用消息中未找到图片")
                event.stop_event()
                event.should_call_llm(False)
                return

            # 处理找到的所有图片
            if found_images:
                # 构建包含所有文件的消息链
                chain: list[BaseMessageComponent] = []
                temp_files = []
                for file_path, filename in found_images:
                    chain.append(Comp.File(file=file_path, name=filename))
                    # 收集临时文件路径，用于后续删除
                    if os.path.abspath(file_path).startswith(
                        os.path.abspath(self.data_dir)
                    ):
                        temp_files.append(file_path)

                try:
                    # 发送所有文件
                    yield event.chain_result(chain)
                except Exception as e:
                    logger.error(f"发送文件时发生错误: {str(e)}")
                    yield event.plain_result(f"发送文件失败: {str(e)}")
                finally:
                    # 根据配置决定是否删除临时文件
                    if self.delete_after_send:
                        for file_path in temp_files:
                            try:
                                if os.path.exists(file_path):
                                    os.remove(file_path)
                                    logger.info(f"删除临时文件: {file_path}")
                            except Exception as e:
                                logger.error(f"删除临时文件时发生错误: {str(e)}")

                event.stop_event()
        except Exception as e:
            logger.error(f"处理回复消息时发生错误: {str(e)}")
            yield event.plain_result(f"处理回复失败: {str(e)}")
            event.stop_event()
            event.should_call_llm(False)

    @filter.command("提取")
    async def convert_command(self, event: AstrMessageEvent):
        """提取图片为可保存的文件格式

        用法: 发送图片或回复包含图片的消息，然后输入 /提取 指令
        """
        event.should_call_llm(False)
        message_chain = event.get_messages()

        # 检查平台是否支持
        if event.get_platform_name() != "aiocqhttp":
            yield event.plain_result("抱歉，该功能仅支持 QQ 平台")
            event.stop_event()
            event.should_call_llm(False)
            return

        found_images = []
        found_reply = False

        # 先收集所有图片和回复
        for msg in message_chain:
            if msg.type == "Image" and isinstance(msg, Image):
                found_images.append(msg)
            elif msg.type == "Reply" and isinstance(msg, Reply):
                found_reply = True
                # 处理回复消息（已经支持多个图片）
                async for result in self.handle_reply_message(event, msg):
                    yield result
                # 回复消息处理完成后直接返回
                return

        # 处理收集到的所有图片
        if found_images:
            # 构建包含所有文件的消息链
            chain: list[BaseMessageComponent] = []
            temp_files = []

            # 确保是AiocqhttpMessageEvent类型
            if not isinstance(event, AiocqhttpMessageEvent):
                yield event.plain_result("抱歉，该功能仅支持 QQ 平台")
                event.stop_event()
                event.should_call_llm(False)
                return

            client = event.bot

            for img_msg in found_images:
                # 处理单个图片
                picture_id = img_msg.file

                try:
                    # 调用 QQ 协议获取图片
                    response = await client.api.call_action(
                        "get_image", file_id=picture_id
                    )
                    localdiskpath = response["file"]

                    # 只通过filetype库判断文件格式
                    file_extension = f".{self.default_extension}"  # 默认扩展名
                    try:
                        kind = filetype.guess(localdiskpath)
                        if kind and kind.extension:
                            file_extension = f".{kind.extension}"
                    except Exception as e:
                        logger.error(f"使用filetype判断图片类型失败: {str(e)}")

                    # 生成唯一的文件名
                    filename = self._generate_filename(file_extension)

                    # 复制图片到我们的临时目录
                    temp_path = os.path.join(self.data_dir, filename)

                    try:
                        shutil.copy2(localdiskpath, temp_path)
                        abs_path = os.path.abspath(temp_path)
                        logger.info(f"图片已复制到临时目录: {abs_path}")
                        chain.append(Comp.File(file=abs_path, name=filename))
                        temp_files.append(abs_path)
                    except Exception as e:
                        logger.error(f"复制图片到临时目录失败: {str(e)}")
                        # 如果复制失败，使用原始路径
                        abs_path = os.path.abspath(localdiskpath)
                        chain.append(Comp.File(file=abs_path, name=filename))
                except Exception as e:
                    logger.error(f"处理图片时发生错误: {str(e)}")
                    yield event.plain_result(f"处理图片失败: {str(e)}")
                    event.stop_event()
                    event.should_call_llm(False)
                    return

            try:
                # 发送所有文件
                yield event.chain_result(chain)
            except Exception as e:
                logger.error(f"发送文件时发生错误: {str(e)}")
                yield event.plain_result(f"发送文件失败: {str(e)}")
            finally:
                # 根据配置决定是否删除临时文件
                if self.delete_after_send:
                    for file_path in temp_files:
                        try:
                            if os.path.exists(file_path):
                                os.remove(file_path)
                                logger.info(f"删除临时文件: {file_path}")
                        except Exception as e:
                            logger.error(f"删除临时文件时发生错误: {str(e)}")

            event.stop_event()
            return

        # 没有找到图片
        yield event.plain_result("请引用表情包或在对话中包含表情包")
        event.stop_event()
        event.should_call_llm(False)

    async def terminate(self):
        """插件终止时的清理操作"""
        # 关闭 aiohttp ClientSession
        if self.session is not None and not self.session.closed:
            try:
                await self.session.close()
                logger.info("已关闭 aiohttp ClientSession")
            except Exception as e:
                logger.error(f"关闭 ClientSession 时发生错误: {str(e)}")

        # 只有当开启了清理临时文件时才执行清理操作
        if self.delete_after_send:
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
        else:
            logger.info("未开启清理临时文件，跳过清理操作")

    async def on_unload(self):
        """框架卸载插件时的钩子方法"""
        await self.terminate()
