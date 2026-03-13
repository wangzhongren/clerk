import asyncio
import openai

async def call_llm_stream(messages, config):
    """流式调用大模型 API"""
    try:
        client = openai.AsyncOpenAI(
            api_key=config.get('api_key'),
            base_url=config.get('base_url', 'https://api.openai.com/v1')
        )
        
        stream = await client.chat.completions.create(
            model=config.get('model', 'gpt-4o-mini'),
            messages=messages,
            temperature=0.2,
            stream=True,
            extra_body={"reasoning_split": True},
        )
        return stream
    except Exception as e:
        raise Exception(f"LLM 调用失败：{str(e)}")

async def call_llm(system_prompt, user_message, config):
    """调用大模型 API"""
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
        
        return response.choices[0].message.content
    except Exception as e:
        raise Exception(f"LLM 调用失败：{str(e)}")