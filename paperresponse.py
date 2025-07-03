import base64
import hashlib
import hmac
import io
import json
import os
import re
import threading
import time
from collections import Counter
from datetime import datetime

import feedparser
import fitz
import lark_oapi as lark
import requests
import schedule
import yaml
from flask import Flask, jsonify, request
from lark_oapi.api.im.v1 import *
from openai import OpenAI
from PIL import Image

lark.APP_ID = '*******************'
lark.APP_SECRET = '*********************'

# 消息去重缓存和线程锁
processed_messages = set()
message_lock = threading.Lock()


def get_arxiv_paper_info(info):
    # 从链接中提取 arXiv ID
    if not info:  # 检查输入是否为空
        return "Empty input"
        
    if 'abs' in info:
        match = re.search(r'arxiv\.org\/abs\/(\d+\.\d+)', info)
    elif 'pdf' in info:
        match = re.search(r'arxiv\.org\/pdf\/(\d+\.\d+)', info)
    else:
        return "Invalid arXiv link"
        
    if not match:  # 检查是否匹配到ID
        return "Invalid arXiv ID format"

    paper_id = match.group(1)

    try:
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
    except Exception as e:
        return f"Error fetching paper info: {str(e)}"


class Paper:
    def __init__(self, path, title='', url='', abs='', authors=None):
        if authors is None:  # 修复可变默认参数的问题
            authors = []
            
        # 检查路径是否存在
        if not os.path.exists(path):
            raise FileNotFoundError(f"PDF file not found: {path}")
            
        self.url = url  # 文章链接
        self.path = path  # pdf路径
        self.section_names = []  # 段落标题
        self.section_texts = {}  # 段落内容
        self.abs = abs
        self.title_page = 0
        
        try:
            if title == '':
                self.pdf = fitz.open(self.path)  # pdf文档
                self.title = self.get_title()
                self.parse_pdf()
            else:
                self.title = title
        except Exception as e:
            raise Exception(f"Error initializing PDF: {str(e)}")
            
        self.authors = authors
        self.roman_num = ["I", "II", 'III', "IV", "V", "VI", "VII", "VIII", "IIX", "IX", "X"]
        self.digit_num = [str(d + 1) for d in range(10)]
        self.first_image = ''

    def parse_pdf(self):
        try:
            self.pdf = fitz.open(self.path)  # pdf文档
            self.text_list = [page.get_text() for page in self.pdf]
            self.all_text = ' '.join(self.text_list)
            self.extract_section_infomation()
            self.section_texts.update({"title": self.title})
        finally:
            if hasattr(self, 'pdf'):
                self.pdf.close()

    def get_chapter_names(self):
        try:
            doc = fitz.open(self.path)  # pdf文档
            text_list = [page.get_text() for page in doc]
            all_text = ''
            for text in text_list:
                all_text += text
            
            chapter_names = []
            for line in all_text.split('\n'):
                if '.' in line:
                    point_split_list = line.split('.')
                    space_split_list = line.split(' ')
                    if 1 < len(space_split_list) < 5:
                        if 1 < len(point_split_list) < 5 and (
                                point_split_list[0] in self.roman_num or point_split_list[0] in self.digit_num):
                            chapter_names.append(line)
            return chapter_names
        finally:
            if 'doc' in locals():
                doc.close()

    def get_title(self):
        max_font_size = 0
        max_string = ""
        max_font_sizes = [0]
        
        try:
            for page_index, page in enumerate(self.pdf):
                text = page.get_text("dict")
                blocks = text.get("blocks", [])
                
                for block in blocks:
                    if block.get("type") == 0 and block.get('lines'):
                        lines = block['lines']
                        if lines and lines[0].get('spans'):
                            spans = lines[0]['spans']
                            if spans:
                                font_size = spans[0].get("size", 0)
                                max_font_sizes.append(font_size)
                                if font_size > max_font_size:
                                    max_font_size = font_size
                                    max_string = spans[0].get("text", "")

            max_font_sizes.sort()
            cur_title = ''
            
            for page_index, page in enumerate(self.pdf):
                text = page.get_text("dict")
                blocks = text.get("blocks", [])
                
                for block in blocks:
                    if block.get("type") == 0 and block.get('lines'):
                        lines = block['lines']
                        if lines and lines[0].get('spans'):
                            spans = lines[0]['spans']
                            if spans:
                                cur_string = spans[0].get("text", "")
                                font_size = spans[0].get("size", 0)
                                
                                if abs(font_size - max_font_sizes[-1]) < 0.3 or abs(font_size - max_font_sizes[-2]) < 0.3:
                                    if len(cur_string) > 4 and "arXiv" not in cur_string:
                                        if cur_title == '':
                                            cur_title += cur_string
                                        else:
                                            cur_title += ' ' + cur_string
                                        self.title_page = page_index

            return cur_title.replace('\n', ' ')
        except Exception as e:
            raise Exception(f"Error extracting title: {str(e)}")

    def extract_section_infomation(self):
        try:
            doc = fitz.open(self.path)
            font_sizes = []
            
            for page in doc:
                blocks = page.get_text("dict").get("blocks", [])
                for block in blocks:
                    if 'lines' not in block:
                        continue
                    for line in block["lines"]:
                        for span in line.get("spans", []):
                            font_sizes.append(span.get("size", 0))
                            
            if not font_sizes:
                raise ValueError("No font sizes found in document")
                
            most_common_size, _ = Counter(font_sizes).most_common(1)[0]
            threshold = most_common_size * 1

            section_dict = {}
            last_heading = None
            subheadings = []
            heading_font = -1
            found_abstract = False
            upper_heading = False
            font_heading = False

            for page in doc:
                blocks = page.get_text("dict").get("blocks", [])
                for block in blocks:
                    if not found_abstract:
                        try:
                            text = json.dumps(block)
                            if re.search(r"\bAbstract\b", text, re.IGNORECASE):
                                found_abstract = True
                                last_heading = "Abstract"
                                section_dict["Abstract"] = ""
                        except:
                            continue
                            
                    if found_abstract:
                        if 'lines' not in block:
                            continue
                        for line in block["lines"]:
                            for span in line.get("spans", []):
                                text = span.get("text", "").strip()
                                size = span.get("size", 0)
                                
                                if not font_heading and text.isupper() and sum(1 for c in text if c.isupper() and ('A' <= c <='Z')) > 4:
                                    upper_heading = True
                                    if "References" in text:
                                        self.section_names = subheadings
                                        self.section_texts = section_dict
                                        return
                                    subheadings.append(text)
                                    if last_heading is not None:
                                        section_dict[last_heading] = section_dict[last_heading].strip()
                                    section_dict[text] = ""
                                    last_heading = text
                                    
                                if not upper_heading and size > threshold and re.match(r"[A-Z][a-z]+(?:\s[A-Z][a-z]+)*", text):
                                    font_heading = True
                                    if heading_font == -1:
                                        heading_font = size
                                    elif heading_font != size:
                                        continue
                                    if "References" in text:
                                        self.section_names = subheadings
                                        self.section_texts = section_dict
                                        return
                                    subheadings.append(text)
                                    if last_heading is not None:
                                        section_dict[last_heading] = section_dict[last_heading].strip()
                                    section_dict[text] = ""
                                    last_heading = text
                                    
                                elif last_heading is not None:
                                    section_dict[last_heading] += " " + text

            self.section_names = subheadings
            self.section_texts = section_dict
            
        except Exception as e:
            raise Exception(f"Error extracting sections: {str(e)}")
        finally:
            if 'doc' in locals():
                doc.close()

def download_pdf(url):
    try:
        if not url:
            raise ValueError("Empty URL")
            
        save_path = os.path.join(os.path.dirname(__file__), os.path.basename(url))
        
        response = requests.get(url, timeout=30)  # 添加超时
        response.raise_for_status()  # 检查响应状态
        
        with open(save_path, 'wb') as f:
            f.write(response.content)
            
        if not os.path.exists(save_path):
            raise FileNotFoundError("Failed to save PDF file")
            
        return save_path
        
    except requests.exceptions.RequestException as e:
        raise Exception(f"Error downloading PDF: {str(e)}")
    except Exception as e:
        raise Exception(f"Error saving PDF: {str(e)}")

def get_paper_pdf_content(url):
    try:
        path = download_pdf(url)
        paper = Paper(path=path)
        paper.parse_pdf()
        
        content = ''
        for key, value in paper.section_texts.items():
            content += f"{key}:{value}:\n"
            
        return content
        
    except Exception as e:
        raise Exception(f"Error getting paper content: {str(e)}")
    finally:
        # 清理临时文件
        if 'path' in locals() and os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass

def get_paper_llm_response(url):
    try:
        content = get_paper_pdf_content(url)
        review_format = """* Overall Review
Please briefly summarize the main points and contributions of this paper.
xxx
* Paper Strength 
Please provide a list of the strengths of this paper, including but not limited to: innovative and practical methodology, insightful empirical findings or in-depth theoretical analysis, 
well-structured review of relevant literature, and any other factors that may make the paper valuable to readers. (Maximum length: 2,000 characters) 
(1) xxx
(2) xxx
(3) xxx
* Paper Weakness 
Please provide a numbered list of your main concerns regarding this paper (so authors could respond to the concerns individually). 
These may include, but are not limited to: inadequate implementation details for reproducing the study, limited evaluation and ablation studies for the proposed method, 
correctness of the theoretical analysis or experimental results, lack of comparisons or discussions with widely-known baselines in the field, lack of clarity in exposition, 
or any other factors that may impede the reader's understanding or benefit from the paper. Please kindly refrain from providing a general assessment of the paper's novelty without providing detailed explanations. (Maximum length: 2,000 characters) 
(1) xxx
(2) xxx
(3) xxx
* Questions To Authors And Suggestions For Rebuttal 
Please provide a numbered list of specific and clear questions that pertain to the details of the proposed method, evaluation setting, or additional results that would aid in supporting the authors' claims. 
The questions should be formulated in a manner that, after the authors have answered them during the rebuttal, it would enable a more thorough assessment of the paper's quality. (Maximum length: 2,000 characters)
*Overall score (1-10)
The paper is scored on a scale of 1-10, with 10 being the full mark, and 6 stands for borderline accept. Then give the reason for your rating.
xxx"""
        language = "Chinese"
        
        openai_client = OpenAI(
            api_key='sk-624001138e2d49999865bbf07e336c60',
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        
        response = openai_client.chat.completions.create(
            model="qwen-plus-latest",
            messages=[
                {"role": "system", "content": f"You are a professional reviewer. Now I will give you a paper. You need to give a complete review opinion according to the following requirements and format:{review_format} Be sure to use {language} answers"},
                {"role": "user", "content": content},
            ],
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        raise Exception(f"Error getting LLM response: {str(e)}")

def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
    try:
        if not data or not data.event or not data.event.message:
            print("Invalid message data")
            return
            
        # 检查消息是否已经处理过（线程安全）
        message_id = data.event.message.message_id
        with message_lock:
            if message_id in processed_messages:
                print(f"Message {message_id} already processed, skipping")
                return
                
            # 添加到已处理消息集合
            processed_messages.add(message_id)
            
            # 限制缓存大小，避免内存泄漏
            if len(processed_messages) > 1000:
                # 移除最旧的一半消息ID
                old_messages = list(processed_messages)[:500]
                processed_messages.difference_update(old_messages)
                print(f"Cleaned message cache, current size: {len(processed_messages)}")
            
        if data.event.message.message_type == "text":
            try:
                res_content = json.loads(data.event.message.content)["text"]
            except json.JSONDecodeError:
                print("Invalid message content format")
                return
        else:
            print("Non-text message received, ignoring")
            return

        if not res_content:
            print("Empty message content")
            return
            
        if 'abs' in res_content:
            match = re.search(r'arxiv\.org\/abs\/(\d+\.\d+)', res_content)
        elif 'pdf' in res_content:
            match = re.search(r'arxiv\.org\/pdf\/(\d+\.\d+)', res_content)
        else:
            print("Invalid arXiv link")
            return
            
        if not match:
            print("Invalid arXiv ID format")
            return

        paper_id = match.group(1)
        url = f'https://arxiv.org/pdf/{paper_id}.pdf'
        
        print(f"Processing paper: {paper_id}")
        text = get_paper_llm_response(url)
        content = json.dumps({"text": text})

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
            
            response = lark_client.im.v1.chat.create(request)
            if not response.success():
                print(f"Failed to send message: {response.code}, {response.msg}")
                return
        else:
            request = (
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
            
            response = lark_client.im.v1.message.reply(request)
            if not response.success():
                print(f"Failed to reply message: {response.code}, {response.msg}")
                return
                
        print(f"Successfully processed and sent response for paper: {paper_id}")
                
    except Exception as e:
        # 记录错误但继续运行
        print(f"Error in message handler: {str(e)}")

event_handler = (
    lark.EventDispatcherHandler.builder("", "")
    .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1)
    .build()
)

lark_client = lark.Client.builder().app_id(lark.APP_ID).app_secret(lark.APP_SECRET).build()
wsClient = lark.ws.Client(
    lark.APP_ID,
    lark.APP_SECRET,
    event_handler=event_handler,
    log_level=lark.LogLevel.DEBUG,
)

def main():
    try:
        wsClient.start()
    except Exception as e:
        print(f"Error starting websocket client: {str(e)}")
        # 可以添加重试逻辑

if __name__ == "__main__":
    main()
