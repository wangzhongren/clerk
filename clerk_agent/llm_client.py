import asyncio
import openai

def _estimate_tokens(text: str) -> int:
    """估算文本的 token 数量（中文约 1.5 字符/token，英文约 4 字符/token）"""
    if not text:
        return 0
    # 简单估算：混合文本平均约 3 字符/token
    return max(1, len(text) // 3)

async def call_llm_stream(messages, config):
    """流式调用大模型 API，返回 (stream, usage_future)"""
    try:
        client = openai.AsyncOpenAI(
            api_key=config.get('api_key'),
            base_url=config.get('base_url', 'https://api.openai.com/v1')
        )
        
        # 计算 prompt token 估算值
        prompt_text = ""
        for msg in messages:
            if msg.get('content'):
                prompt_text += msg['content']
        estimated_prompt_tokens = _estimate_tokens(prompt_text)
        
        response = await client.chat.completions.create(
            model=config.get('model', 'gpt-4o-mini'),
            messages=messages,
            temperature=0.2,
            stream=True,
            extra_body={"reasoning_split": True},
        )
        
        # 创建一个 future 来存储最终的 usage 信息
        usage_future = asyncio.Future()
        
        async def _stream_with_usage():
            total_usage = None
            completion_text = ""
            async for chunk in response:
                # 检查是否有 usage 信息（通常在最后一个 chunk）
                if hasattr(chunk, 'usage') and chunk.usage is not None:
                    total_usage = {
                        'prompt_tokens': chunk.usage.prompt_tokens,
                        'completion_tokens': chunk.usage.completion_tokens,
                        'total_tokens': chunk.usage.total_tokens
                    }
                # 累积 completion 文本用于估算
                if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                    if chunk.choices[0].delta.content:
                        completion_text += chunk.choices[0].delta.content
                yield chunk
            
            # 设置 usage 信息：优先使用 API 返回的，否则使用估算值
            if total_usage:
                usage_future.set_result(total_usage)
            else:
                # 使用估算值
                estimated_completion_tokens = _estimate_tokens(completion_text)
                estimated_usage = {
                    'prompt_tokens': estimated_prompt_tokens,
                    'completion_tokens': estimated_completion_tokens,
                    'total_tokens': estimated_prompt_tokens + estimated_completion_tokens
                }
                usage_future.set_result(estimated_usage)
        
        return _stream_with_usage(), usage_future
    except Exception as e:
        raise Exception(f"LLM 调用失败：{str(e)}")

async def call_llm(system_prompt, user_message, config):
    """调用大模型 API，返回 (content, usage)"""
    try:
        client = openai.AsyncOpenAI(
            api_key=config.get('api_key'),
            base_url=config.get('base_url', 'https://api.openai.com/v1')
        )
        
        response = await client.chat.completions.create(
            model=config.get('model', 'gpt-4o-mini'),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.2
        )
        
        content = response.choices[0].message.content
        usage = {
            'prompt_tokens': response.usage.prompt_tokens if response.usage else 0,
            'completion_tokens': response.usage.completion_tokens if response.usage else 0,
            'total_tokens': response.usage.total_tokens if response.usage else 0
        }
        
        return content, usage
    except Exception as e:
        raise Exception(f"LLM 调用失败：{str(e)}")