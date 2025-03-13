#!/usr/bin/env python3
# coding:utf-8

import base64
import hashlib
import hmac
import time
from datetime import datetime

import requests
import schedule

# 飞书机器人配置
WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxxxxxxxxx"
WEBHOOK_SECRET = "xxxxxxxxxxxxxxxxxxxxxxx"

def gen_sign(secret: str) -> tuple[str, str]:
    """生成飞书机器人签名"""
    timestamp = int(datetime.now().timestamp())
    string_to_sign = f'{timestamp}\n{secret}'
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"), 
        digestmod=hashlib.sha256
    ).digest()
    sign = base64.b64encode(hmac_code).decode('utf-8')
    return str(timestamp), str(sign)

def get_paper_info() -> list:
    """获取HuggingFace每日论文信息"""
    API_URL = 'https://huggingface.co/api/daily_papers'
    response = requests.get(f"{API_URL}?limit=100")
    response.raise_for_status()
    data = response.json()
    
    now_time = time.time()
    time_48h_ago = now_time - 48 * 60 * 60
    
    recent_papers = [
        paper for paper in data 
        if time.mktime(time.strptime(paper['publishedAt'], '%Y-%m-%dT%H:%M:%S.%fZ')) > time_48h_ago
    ]
    ready_papers = []
    for paper in recent_papers:
        try:
            paper_info = map_paper_info(paper)
            ready_papers.append(paper_info)
        except Exception as e:
            print(f"Error processing paper: {paper['paper']['id']}. Error: {e}")
    
    return ready_papers[:5]

def map_paper_info(paper_info: dict) -> dict:
    """整理论文信息为指定格式"""
    paper = paper_info['paper']
    authors = [author['name'] for author in paper["authors"]]
    return {
        "title": paper["title"],
        "authors": ", ".join(authors),
        "summary": paper["summary"],
        "pdf_url": 'https://arxiv.org/pdf/' + paper['id'],
    }

def generate_card_elements(num: int, paper_info: dict) -> list:
    """生成飞书消息卡片元素"""
    return [{
        "tag": "div",
        "text": {
            "content": f"**我的今日AI论文 {num}**",
            "tag": "lark_md"
        }
    }, {
        "tag": "div",
        "text": {
            "content": f"**标题**：{paper_info['title']}",
            "tag": "lark_md"
        }
    }, {
        "tag": "div",
        "text": {
            "content": f"**摘要**：{paper_info['summary']}",
            "tag": "lark_md"
        }
    }, {
        "tag": "div",
        "text": {
            "content": f"**地址**：{paper_info['pdf_url']}",
            "tag": "lark_md"
        }
    }]

def send_feishu_message(timestamp: str, sign: str, elements: list) -> None:
    """发送飞书消息"""
    params = {
        "timestamp": timestamp,
        "sign": sign,
        "msg_type": "interactive",
        "card": {
            "config": {
                "wide_screen_mode": True
            },
            "elements": elements
        }
    }
    
    headers = {"Content-Type": "application/json"}
    resp = requests.post(WEBHOOK_URL, headers=headers, json=params)
    resp.raise_for_status()
    result = resp.json()
    
    if result.get("code") and result.get("code") != 0:
        print(f"发送失败：{result['msg']}")
        return
    print("消息发送成功")

def main():
    """主函数"""
    # 使用schedule库实现定时任务
    
    def job():
        timestamp, sign = gen_sign(WEBHOOK_SECRET)
        papers = get_paper_info()
        
        for num, paper in enumerate(papers):
            time.sleep(2)  # 避免请求过快
            print(paper)
            
            elements = generate_card_elements(num, paper)
            send_feishu_message(timestamp, sign, elements)
    
    # 设置每天上午10:30执行任务
    schedule.every().day.at("10:30").do(job)
    
    # 持续运行，等待定时任务
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    main()