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
    
    import re

    def get_prompt_descriptions(self, agent: str = "default") -> str:
        """从函数签名生成 100% 准确的 Few-shot 示例提示词"""
        descriptions = []
        functions = self._functions.get(agent, {})
        
        for name, info in functions.items():
            f_str = info['function_str']
            prompt_text = info['prompt']
            
            # --- 优化点：不再使用正则，而是基于 ast 逻辑提取纯净参数名 ---
            try:
                # 简单解析括号内的参数，去掉默认值和星号
                # 这种方法比直接 match 完整函数名更稳
                params_part = f_str.split('(', 1)[1].rsplit(')', 1)[0]
                # 分割并清洗，例如 "path, mode='r'" -> "path, mode"
                clean_params = []
                for p in params_part.split(','):
                    p = p.strip()
                    if not p: continue
                    # 只保留变量名部分，去掉 = 及之后的默认值
                    param_name = p.split('=')[0].strip().replace('*', '')
                    if param_name:
                        clean_params.append(param_name)
                
                body_fields = ",".join(clean_params)
                
                # 构造 CDATA 示例块
                cdata_examples = ""
                for p in clean_params:
                    # 加入你的本地化存储记忆 [2026-02-26]
                    if "path" in p.lower():
                        val = "./config/config.json"
                    elif "content" in p.lower():
                        val = '{"key": "value"}'
                    else:
                        val = f"sample_{p}"
                    cdata_examples += f"    <![CDATA[ {val} ]]>\n"
                
                example = (
                    f"### 函数: {name}\n"
                    f"功能描述: {prompt_text}\n"
                    f"严格输出格式示例:\n"
                    f"<function-call>\n"
                    f"  <{name} _body_fields=\"{body_fields}\">\n"
                    f"{cdata_examples.rstrip()}\n"
                    f"  </{name}>\n"
                    f"</function-call>"
                )
                descriptions.append(example)
            except Exception:
                descriptions.append(f"### {f_str}\n功能描述: {prompt_text}")

        return "\n\n---\n\n".join(descriptions)
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

import xml.etree.ElementTree as ET
from typing import List, Dict, Any
import traceback


import re
import xml.dom.minidom
from typing import List, Dict

import re
import xml.dom.minidom
from typing import List, Dict

def parse_function_calls(text: str, agent: str = "default") -> List[Dict]:
    function_calls = []
    
    # 1. 提取 <function-call> 块
    blocks = re.findall(r'<function-call>(.*?)</function-call>', text, re.DOTALL)
    
    # 容错：未闭合标签检测
    if text.count('<function-call>') > len(blocks):
        function_calls.append({
            'name': 'unknown_wrapper',
            'error': "检测到未闭合的 <function-call> 标签",
            'type': 'syntax_error'
        })

    for block in blocks:
        # 预先尝试用正则抓取标签名，以防 XML 解析彻底崩溃
        # 匹配 <tag_name _body_fields=... 或 <tag_name>
        tag_match = re.search(r'<([a-zA-Z0-9_]+)[\s>]', block.strip())
        tentative_name = tag_match.group(1) if tag_match else "unknown_function"

        try:
            # 包装并解析
            dom = xml.dom.minidom.parseString(f"<root>{block}</root>")
            root = dom.documentElement
            
            for func_node in root.childNodes:
                if func_node.nodeType != func_node.ELEMENT_NODE:
                    continue
                
                func_name = func_node.tagName
                fields_str = func_node.getAttribute('_body_fields')
                field_names = [f.strip() for f in fields_str.split(',') if f.strip()]
                
                # 提取 CDATA 块
                cdata_values = [
                    node.data for node in func_node.childNodes 
                    if node.nodeType == node.CDATA_SECTION_NODE
                ]
                
                # 校验数量
                if field_names and len(field_names) != len(cdata_values):
                    function_calls.append({
                        'name': func_name,
                        'error': f"字段数({len(field_names)})与数据块数({len(cdata_values)})不符",
                        'type': 'validation_error'
                    })
                    continue

                # 映射参数
                kwargs = {name: value.strip() for name, value in zip(field_names, cdata_values)}
                
                function_calls.append({
                    'name': func_name,
                    'kwargs': kwargs
                })

        except Exception as e:
            # 哪怕解析失败，也要把刚才正则抢救到的名字传回去
            function_calls.append({
                'name': tentative_name,
                'error': f"XML 解析失败: {str(e)}",
                'type': 'parse_error',
                'raw_segment': block[:100] # 保留前100个字符方便Debug
            })
            
    return function_calls


def _parse_xml_node_to_dict(node) -> Any:
    """辅助函数：将 XML 节点递归转为字典"""
    res = {}
    for child in node:
        if len(child) > 0:
            res[child.tag] = _parse_xml_node_to_dict(child)
        else:
            res[child.tag] = _infer_type(child.text)
    return res

def _infer_type(text: Optional[str]) -> Any:
    """简单的类型推断"""
    if text is None: return None
    t = text.strip()
    if t.lower() == 'true': return True
    if t.lower() == 'false': return False
    try:
        if '.' in t: return float(t)
        return int(t)
    except ValueError:
        return t