import inspect
import ast
import traceback
from typing import Dict, List, Callable, Any, Optional
import xml.etree.ElementTree as ET
from xml.parsers.expat import ExpatError

class FunctionRegistry:
    """函数注册表，支持按 agent 隔离注册"""
    
    def __init__(self):
        # 结构: {agent_name: {func_name: func_info}}
        self._functions: Dict[str, Dict[str, Dict]] = {}
    
    def register(self, name: str, prompt: str, function: Callable, function_str: str = None, agent: str = "default"):
        """注册函数
        
        Args:
            name: 函数名称
            prompt: 方法提示词说明
            function: 真实的方法
            function_str: 方法字符串表示，如果为None则自动从源码生成
            agent: 所属 agent 名称，默认为 "default"
        """
        if function_str is None:
            # 自动从函数源码生成字符串表示
            function_str = self._generate_function_str_from_source(function, name)
        
        if agent not in self._functions:
            self._functions[agent] = {}
        
        self._functions[agent][name] = {
            "prompt": prompt,
            "function_str": function_str,
            "function": function
        }
    
    def _generate_function_str_from_source(self, func: Callable, name: str) -> str:
        """从函数源码自动生成函数字符串表示"""
        try:
            # 获取函数源码
            source = inspect.getsource(func)
            
            # 解析函数定义
            tree = ast.parse(source)
            func_def = tree.body[0]
            
            if not isinstance(func_def, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return f"{name}(...)"
            
            # 提取参数
            args = func_def.args
            params = []
            
            # 位置参数
            for arg in args.args:
                params.append(arg.arg)
            
            # 可变位置参数 (*args)
            if args.vararg:
                params.append(f"*{args.vararg.arg}")
            
            # 关键字参数
            for arg in args.kwonlyargs:
                default = None
                # 查找对应的默认值
                for i, kw_default in enumerate(args.kw_defaults):
                    if i < len(args.kwonlyargs) and args.kwonlyargs[i].arg == arg.arg:
                        if kw_default is not None:
                            default = ast.unparse(kw_default) if hasattr(ast, 'unparse') else self._format_default(kw_default)
                        break
                
                if default is not None:
                    params.append(f"{arg.arg}={default}")
                else:
                    params.append(arg.arg)
            
            # 可变关键字参数 (**kwargs)
            if args.kwarg:
                params.append(f"**{args.kwarg.arg}")
            
            return f"{name}({', '.join(params)})"
            
        except (SyntaxError, IndexError, AttributeError):
            # 如果源码解析失败，回退到签名方式
            return self._generate_function_str_from_signature(func, name)
    
    def _format_default(self, node) -> str:
        """格式化默认值节点"""
        if isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Name) and node.id == 'None':
            return 'None'
        elif isinstance(node, ast.Str):
            return repr(node.s)
        elif isinstance(node, ast.Num):
            return repr(node.n)
        elif isinstance(node, ast.NameConstant):
            return repr(node.value)
        else:
            # 对于复杂表达式，返回占位符
            return "..."
    
    def _generate_function_str_from_signature(self, func: Callable, name: str) -> str:
        """使用inspect.signature生成函数字符串（备用方案）"""
        try:
            sig = inspect.signature(func)
            params = []
            for param_name, param in sig.parameters.items():
                if param.default == inspect.Parameter.empty:
                    if param.kind == param.VAR_POSITIONAL:
                        params.append(f"*{param_name}")
                    elif param.kind == param.VAR_KEYWORD:
                        params.append(f"**{param_name}")
                    else:
                        params.append(param_name)
                else:
                    params.append(f"{param_name}={param.default!r}")
            
            return f"{name}({', '.join(params)})"
        except:
            return f"{name}(...)"
    
    def get_function(self, name: str, agent: str = "default") -> Optional[Dict]:
        """获取注册的函数信息"""
        return self._functions.get(agent, {}).get(name)
    
    def get_all_functions(self, agent: str = "default") -> Dict[str, Dict]:
        """获取指定 agent 的所有注册函数"""
        return self._functions.get(agent, {}).copy()
    
    def get_all_agents(self) -> List[str]:
        """获取所有已注册的 agent 名称"""
        return list(self._functions.keys())
    
    def get_prompt_descriptions(self, agent: str = "default") -> str:
        """获取指定 agent 所有函数的提示词描述"""
        descriptions = []
        for name, info in self._functions.get(agent, {}).items():
            descriptions.append(f"{info['function_str']} - {info['prompt']}")
        return "\n".join(descriptions)
    
    def execute_function(self, name: str, *args, agent: str = "default", **kwargs) -> Any:
        """执行注册的函数"""
        func_info = self.get_function(name, agent)
        if not func_info:
            raise ValueError(f"Function '{name}' is not registered for agent '{agent}'")
        
        return func_info['function'](*args, **kwargs)

# 全局注册表实例
global_registry = FunctionRegistry()

def _parse_xml_value(element) -> Any:
    """递归解析XML元素的值"""
    # 如果元素没有子元素，返回文本内容
    if len(element) == 0:
        text = element.text or ""
        text = text.strip()
        if not text:
            return None
        
        # 尝试类型推断
        # 布尔值
        if text.lower() == 'true':
            return True
        elif text.lower() == 'false':
            return False
        # 数字
        try:
            if '.' in text:
                return float(text)
            else:
                return int(text)
        except ValueError:
            pass
        # 字符串
        return text
    
    # 如果有子元素，构建字典或列表
    result = {}
    for child in element:
        child_value = _parse_xml_value(child)
        # 处理同名子元素（数组）
        if child.tag in result:
            if isinstance(result[child.tag], list):
                result[child.tag].append(child_value)
            else:
                result[child.tag] = [result[child.tag], child_value]
        else:
            result[child.tag] = child_value
    
    return result

from typing import List, Dict
from bs4 import BeautifulSoup
import re
import traceback

from typing import List, Dict
from bs4 import BeautifulSoup
import re
import traceback

import re
from typing import List, Dict, Any

def parse_xml_to_dict(xml_content: str) -> Dict[str, Any]:
    """
    递归解析 XML 结构为字典。
    支持：<tag><subtag>value</subtag></tag> -> {'tag': {'subtag': 'value'}}
    """
    result = {}
    # 匹配 <tag>content</tag>，不处理自闭合标签
    pattern = re.compile(r'<(\w+)\s*>(.*?)</\1>', re.DOTALL)
    matches = pattern.findall(xml_content)
    
    if not matches:
        # 如果没有子标签了，返回去前后的字符串内容
        return xml_content.strip()
    
    for tag, content in matches:
        parsed_content = parse_xml_to_dict(content)
        # 如果有重复标签（如列表），可以考虑转为 list，这里默认覆盖或嵌套
        result[tag] = parsed_content
        
    return result

def parse_function_calls(text: str) -> List[Dict]:
    """
    使用正则严格解析 <function-call>。
    即便没有闭合标签，也会将错误封装成字典返回。
    """
    function_calls = []

    # 1. 定义内部递归解析逻辑
    def extract_tags_recursive(content: str) -> Any:
        # 匹配 <tag>内容</tag>
        # \1 保证了起始和结束标签名必须完全一致
        pattern = re.compile(r'<(\w+)>(.*?)</\1>', re.DOTALL)
        matches = pattern.findall(content)
        
        if not matches:
            # 容错：如果还残留 < 符号，说明可能存在未闭合标签
            if '<' in content:
                orphan = re.search(r'<(\w+)>', content)
                if orphan:
                    raise ValueError(f"发现未闭合标签: <{orphan.group(1)}>，请检查 XML 结构")
            return content.strip()
        
        result = {}
        for tag, inner_content in matches:
            result[tag] = extract_tags_recursive(inner_content)
        return result

    # 2. 寻找所有 <function-call> 的起始位置
    # 这样即使没有结束标签，我们也能定位到错误
    start_tags = list(re.finditer(r'<function-call>', text))
    
    for i, start_match in enumerate(start_tags):
        start_pos = start_match.start()
        # 截取当前标签到文本末尾，寻找最近的一个闭合标签
        remaining_text = text[start_pos:]
        block_match = re.search(r'<function-call>(.*?)</function-call>', remaining_text, re.DOTALL)
        
        try:
            if not block_match:
                # 场景：有开头没结尾
                raise ValueError("检测到 <function-call> 标签未闭合")
            
            block_content = block_match.group(1)
            # 解析内部结构 (例如 <execute_shell><command>...</command></execute_shell>)
            full_structure = extract_tags_recursive(block_content)
            
            if isinstance(full_structure, dict):
                for func_name, params in full_structure.items():
                    # 按照你的要求，封装进 kwargs
                    kwargs = {}
                    if isinstance(params, dict):
                        kwargs.update(params)
                    else:
                        # 如果函数标签内部直接是文本内容
                        kwargs['content'] = params
                    
                    function_calls.append({
                        'name': func_name,
                        'args': [],
                        'kwargs': kwargs
                    })
            else:
                raise ValueError("未能在 <function-call> 中找到有效的函数名标签")

        except Exception as e:
            # 发生任何解析错误时，封装成错误 JSON
            error_info = {
                'error': str(e),
                'error_type': type(e).__name__,
                'error_msg': traceback.format_exc(),
                'raw_segment': remaining_text[:100] + "..." # 保存出错部分的上下文
            }
            function_calls.append(error_info)
            
    return function_calls