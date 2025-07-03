import base64
import hashlib
import hmac
import json
import re
import time
from datetime import datetime

import feedparser
import lark_oapi as lark
import requests
import schedule
import yaml
from flask import Flask, jsonify, request
from lark_oapi.api.im.v1 import *

lark.APP_ID = '************'
lark.APP_SECRET = '************'


def get_arxiv_paper_info(info):
    # 从链接中提取 arXiv ID
    if 'abs' in info:
        match = re.search(r'arxiv\.org\/abs\/(\d+\.\d+)', info)
    elif 'pdf' in info:
        match = re.search(r'arxiv\.org\/pdf\/(\d+\.\d+)', info)
    else:
        return "Invalid arXiv link"

    paper_id = match.group(1)

    # 构建 API 请求 URL
    url = f'http://export.arxiv.org/api/query?id_list={paper_id}'

    # 发送请求
    feed = feedparser.parse(url)

    if not feed.entries:
        return "Paper not found"

    entry = feed.entries[0]

    title = entry.title.strip()
    authors = [author.name for author in entry.authors]
    summary = entry.summary.strip()

    return {
        'title': title,
        'authors': authors,
        'abstract': summary
    }


# 注册接收消息事件，处理接收到的消息。
# Register event handler to handle received messages.
# https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/events/receive
def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
    res_content = ""
    if data.event.message.message_type == "text":
        res_content = json.loads(data.event.message.content)["text"]
    else:
        res_content = "解析消息失败，请发送文本消息\nparse message failed, please send text message"
    paper_info = get_arxiv_paper_info(res_content)
    
    text = f"Title: {paper_info['title']}\n\nAuthors: {', '.join(paper_info['authors'])}\n\nAbstract: {paper_info['abstract']}"
    
    content = json.dumps(
        {
            "text": text
        }
    )

    if data.event.message.chat_type == "p2p":
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(data.event.message.chat_id)
                .msg_type("text")
                .content(content)
                .build()
            )
            .build()
        )
        # 使用OpenAPI发送消息
        # Use send OpenAPI to send messages
        # https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/create
        response = client.im.v1.chat.create(request)

        if not response.success():
            raise Exception(
                f"client.im.v1.chat.create failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}"
            )
    else:
        request: ReplyMessageRequest = (
            ReplyMessageRequest.builder()
            .message_id(data.event.message.message_id)
            .request_body(
                ReplyMessageRequestBody.builder()
                .content(content)
                .msg_type("text")
                .build()
            )
            .build()
        )
        # 使用OpenAPI回复消息
        # Reply to messages using send OpenAPI
        # https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/reply
        response: ReplyMessageResponse = client.im.v1.message.reply(request)
        if not response.success():
            raise Exception(
                f"client.im.v1.message.reply failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}"
            )


# 注册事件回调
# Register event handler.
event_handler = (
    lark.EventDispatcherHandler.builder("", "")
    .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1)
    .build()
)


# 创建 LarkClient 对象，用于请求OpenAPI, 并创建 LarkWSClient 对象，用于使用长连接接收事件。
# Create LarkClient object for requesting OpenAPI, and create LarkWSClient object for receiving events using long connection.
client = lark.Client.builder().app_id(lark.APP_ID).app_secret(lark.APP_SECRET).build()
wsClient = lark.ws.Client(
    lark.APP_ID,
    lark.APP_SECRET,
    event_handler=event_handler,
    log_level=lark.LogLevel.DEBUG,
)


def main():
    #  启动长连接，并注册事件处理器。
    #  Start long connection and register event handler.
    wsClient.start()


if __name__ == "__main__":
    main()
