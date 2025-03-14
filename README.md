# Daily Papers 飞书同步机器人

## 项目简介  
本项目通过飞书机器人实现[Hugging Face Daily Papers](https://github.com/huggingface/blog/blob/main/daily-papers.md)的每日自动同步，帮助团队高效追踪AI领域（尤其是LLM方向）的前沿研究。机器人支持论文标题、摘要、作者等内容的自动抓取与格式化推送。


## 功能特性  
✅ **每日定时推送**：基于定时触发器实现自动化同步  
✅ **多格式支持**：支持文本、Markdown、富文本卡片等多种消息格式  
✅ **灵活配置**：可自定义推送时间、目标群组、内容筛选规则  
✅ **错误重试机制**：网络异常时自动重试3次并记录日志  

## 快速使用

1. 拿到飞书机器人的Webhook地址和签名密钥  
2. 将Webhook地址和签名密钥填写在代码中
3. 执行`python main.py`


## 消息示例  
```markdown
**我的今日AI论文 0**

**标题**：Block Diffusion: Interpolating Between Autoregressive and Diffusion Language Models

**作者**：Marianne Arriola, Aaron Gokaslan, Justin T Chiu, Zhihan Yang, Zhixuan Qi, Jiaqi Han, Subham Sekhar Sahoo, Volodymyr Kuleshov

**摘要**：Diffusion language models offer unique benefits over autoregressive models
due to their potential for parallelized generation and controllability, yet
they lag in likelihood modeling and are limited to fixed-length generation. In
this work, we introduce a class of block diffusion language models that
interpolate between discrete denoising diffusion and autoregressive models.
Block diffusion overcomes key limitations of both approaches by supporting
flexible-length generation and improving inference efficiency with KV caching
and parallel token sampling. We propose a recipe for building effective block
diffusion models that includes an efficient training algorithm, estimators of
gradient variance, and data-driven noise schedules to minimize the variance.
Block diffusion sets a new state-of-the-art performance among diffusion models
on language modeling benchmarks and enables generation of arbitrary-length
sequences. We provide the code, along with the model weights and blog post on
the project page: https://m-arriola.com/bd3lms/

**关键词**：diffusion language models, autoregressive models, parallelized generation, controllability, likelihood modeling, fixed-length generation, block diffusion language models, discrete denoising diffusion, flexible-length generation, inference efficiency, KV caching, parallel token sampling, efficient training algorithm, gradient variance estimators, data-driven noise schedules, arbitrary-length sequences

**地址**：https://arxiv.org/pdf/2503.09573
```