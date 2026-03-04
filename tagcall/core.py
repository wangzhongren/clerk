import inspect
import ast
from typing import Dict, List, Callable, Any, Optional
from bs4 import BeautifulSoup
import re

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
            function_str: 方法字符串，如果为None则自动从源码生成
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

# 全球注册表实例
global_registry = FunctionRegistry()

def _parse_ast_value(node: ast.expr) -> Any:
    """递归地将 AST 节点转换为 Python 对象"""
    if isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.Str):  # 兼容 Python < 3.8
        return node.s
    elif isinstance(node, ast.Num):  # 兼容 Python < 3.8
        return node.n
    elif isinstance(node, ast.Name):
        # 如果参数是变量名而非字面量，返回其名称字符串
        if node.id in ('True', 'False', 'None'):
            return {'True': True, 'False': False, 'None': None}[node.id]
        return f"<variable: {node.id}>"
    elif isinstance(node, ast.List):
        return [_parse_ast_value(el) for el in node.elts]
    elif isinstance(node, ast.Tuple):
        return tuple(_parse_ast_value(el) for el in node.elts)
    elif isinstance(node, ast.Dict):
        return {_parse_ast_value(k): _parse_ast_value(v) for k, v in zip(node.keys, node.values)}
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        # 处理负数
        return -_parse_ast_value(node.operand)
    elif isinstance(node, ast.BinOp):  # 处理二元操作，如 a + b
        left = _parse_ast_value(node.left)
        right = _parse_ast_value(node.right)
        op = type(node.op)
        if op == ast.Add:
            return left + right if isinstance(left, (int, float)) and isinstance(right, (int, float)) else f"{left} + {right}"
        elif op == ast.Sub:
            return left - right if isinstance(left, (int, float)) and isinstance(right, (int, float)) else f"{left} - {right}"
        elif op == ast.Mult:
            return left * right if isinstance(left, (int, float)) and isinstance(right, (int, float)) else f"{left} * {right}"
        elif op == ast.Div:
            return left / right if isinstance(left, (int, float)) and isinstance(right, (int, float)) else f"{left} / {right}"
        else:
            return f"{left} {op.__name__} {right}"
    elif isinstance(node, ast.Call):  # 处理函数调用作为参数
        return f"<call: {ast.unparse(node)}>" if hasattr(ast, 'unparse') else "<call>"
    else:
        # 对于无法解析的复杂表达式，返回原始源码
        return ast.unparse(node) if hasattr(ast, 'unparse') else repr(node)

def _get_full_func_name(node):
    """获取完整的函数名，处理嵌套属性如 obj.method 或 module.submodule.function"""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{_get_full_func_name(node.value)}.{node.attr}"
    else:
        return repr(node)

def parse_function_calls(text: str) -> List[Dict]:
    """
    解析函数调用文本
    
    使用 ast 模块替代手动字符串分割，以 robustly 处理多行字符串、转义字符和复杂参数。
    
    Args:
        text: 包含<function-call>标签的文本
        
    Returns:
        List[Dict]: 解析出的函数调用列表
    """
    soup = BeautifulSoup(text, 'html.parser')
    function_call_tags = soup.find_all('function-call')
    
    if not function_call_tags:
        return []
    
    all_calls = []
    
    for tag in function_call_tags:
        # 获取标签内的原始文本
        raw_content = tag.get_text()
        
        # 清理可能存在的周围空白，但不要过度修改内部格式
        code_block = raw_content.strip()
        
        if not code_block:
            continue
            
        try:
            # 尝试直接解析
            tree = ast.parse(code_block)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                    call_node = node.value
                    
                    # 改进函数名提取逻辑
                    func_name = _get_full_func_name(call_node.func)
                    
                    args = []
                    kwargs = {}
                    
                    # 解析位置参数
                    for arg in call_node.args:
                        args.append(_parse_ast_value(arg))
                        
                    # 解析关键字参数
                    for kw in call_node.keywords:
                        key = kw.arg
                        value = _parse_ast_value(kw.value)
                        kwargs[key] = value
                    
                    all_calls.append({
                        'name': func_name,
                        'args': args,
                        'kwargs': kwargs
                    })
                    
        except SyntaxError:
            # 如果直接解析失败，尝试使用正则表达式预处理
            try:
                # 使用正则表达式提取函数调用
                calls = _extract_function_calls_regex(code_block)
                all_calls.extend(calls)
            except Exception as e:
                print(f"正则表达式解析也失败：{e}")
                print(f"问题内容片段（前200字符）：{repr(code_block[:200])}")
                continue
        except Exception as e:
            print(f"解析过程中发生未知错误：{e}")
            continue

    return all_calls

def _extract_function_calls_regex(code_block: str) -> List[Dict]:
    """
    使用正则表达式提取函数调用，特别处理多行字符串
    """
    # 匹配函数调用模式，包括处理多行字符串
    pattern = r'(\w+(?:\.\w+)*)\s*\((.*?)\)'
    
    # 找到所有的函数调用
    # 首先找到所有可能的函数调用边界
    result = []
    
    # 更智能的函数调用解析器
    calls = _parse_function_calls_smart(code_block)
    for call in calls:
        result.append(call)
    
    return result

def _parse_function_calls_smart(code_block: str) -> List[Dict]:
    """
    智能解析函数调用，能够处理多行字符串和复杂的参数
    """
    result = []
    i = 0
    length = len(code_block)
    
    while i < length:
        # 寻找函数名
        func_match = re.search(r'\b([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*)\s*\(', code_block[i:])
        if not func_match:
            break
            
        func_start = i + func_match.start()
        func_name = func_match.group(1)
        paren_start = func_start + len(func_match.group()) - 1  # 定位到左括号
        
        # 找到匹配的右括号，考虑嵌套括号和字符串
        paren_depth = 1
        j = paren_start + 1
        quote_char = None
        escaped = False
        
        while j < length and paren_depth > 0:
            char = code_block[j]
            
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif quote_char and char == quote_char:
                quote_char = None
            elif not quote_char and char in ['"', "'"]:
                quote_char = char
                # 检查是否是三引号
                if j + 2 < length and code_block[j:j+3] in ['"""', "'''"]:
                    quote_char = code_block[j:j+3]
                    j += 2
            elif quote_char == '"""' or quote_char == "'''":
                if j + 2 < length and code_block[j:j+3] == quote_char:
                    quote_char = None
                    j += 2
            elif not quote_char:
                if char == '(':
                    paren_depth += 1
                elif char == ')':
                    paren_depth -= 1
            
            j += 1
        
        if paren_depth == 0:
            # 提取参数部分
            args_str = code_block[paren_start + 1:j - 1]
            
            # 解析参数
            args, kwargs = _parse_arguments(args_str)
            
            result.append({
                'name': func_name,
                'args': args,
                'kwargs': kwargs
            })
            
            i = j  # 移动到下一个可能的位置
        else:
            # 如果括号不匹配，移动到下一个可能的函数调用
            i = func_start + 1
    
    return result

def _parse_arguments(args_str: str) -> tuple[list, dict]:
    """
    解析函数参数字符串
    """
    args = []
    kwargs = {}
    
    if not args_str.strip():
        return args, kwargs
    
    # 智能分割参数，考虑嵌套结构和字符串
    params = _smart_split_params(args_str)
    
    for param in params:
        param = param.strip()
        if '=' in param and not _is_in_string_or_brackets(param, '='):
            # 这是一个关键字参数
            eq_index = param.index('=')
            key = param[:eq_index].strip()
            value_str = param[eq_index + 1:].strip()
            kwargs[key] = _evaluate_param(value_str)
        else:
            # 这是一个位置参数
            args.append(_evaluate_param(param))
    
    return args, kwargs

def _smart_split_params(params_str: str) -> list:
    """
    智能分割参数，考虑嵌套括号、列表、字典和字符串
    """
    result = []
    current = ""
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    quote_char = None
    escaped = False
    
    for char in params_str:
        if escaped:
            current += char
            escaped = False
        elif char == '\\':
            current += char
            escaped = True
        elif quote_char and char == quote_char[0]:
            # 检查是否是结束的引号
            if quote_char in ['"""', "'''"]:  # 三引号
                if len(current) >= 3 and current.endswith(quote_char[-3:]):
                    # 检查当前是否是以三引号结尾
                    if len(current) >= 3 and current[-3:] == quote_char:
                        quote_char = None
                        current += char
                    else:
                        current += char
                else:
                    current += char
            else:  # 普通引号
                quote_char = None
                current += char
        elif quote_char:
            current += char
        elif quote_char is None and char in ['"', "'"]:
            # 检查是否是三引号开始
            pos = len(current)
            remaining = params_str[pos:pos+3]
            if remaining.startswith('"""') or remaining.startswith("'''"):
                quote_char = params_str[pos:pos+3]
                current += quote_char
            else:
                quote_char = char
                current += char
        elif char == '(':
            paren_depth += 1
            current += char
        elif char == ')':
            paren_depth -= 1
            current += char
        elif char == '[':
            bracket_depth += 1
            current += char
        elif char == ']':
            bracket_depth -= 1
            current += char
        elif char == '{':
            brace_depth += 1
            current += char
        elif char == '}':
            brace_depth -= 1
            current += char
        elif char == ',' and paren_depth == 0 and bracket_depth == 0 and brace_depth == 0 and quote_char is None:
            result.append(current.strip())
            current = ""
        else:
            current += char
    
    if current.strip():
        result.append(current.strip())
    
    return result

def _is_in_string_or_brackets(s: str, target_pos: int) -> bool:
    """
    检查某个位置是否在字符串或括号内
    """
    quote_char = None
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    escaped = False
    
    for i, char in enumerate(s):
        if i == target_pos:
            return quote_char is not None or paren_depth > 0 or bracket_depth > 0 or brace_depth > 0
        
        if escaped:
            escaped = False
        elif char == '\\':
            escaped = True
        elif quote_char and char == quote_char[0]:
            # 检查三引号结束
            if quote_char in ['"""', "'''"] and i + 2 < len(s) and s[i:i+3] == quote_char:
                quote_char = None
            elif quote_char == char:
                quote_char = None
        elif quote_char is None and char in ['"', "'"]:
            # 检查是否是三引号
            if i + 2 < len(s) and s[i:i+3] in ['"""', "'''"]:
                quote_char = s[i:i+3]
            else:
                quote_char = char
        elif char == '(' and quote_char is None:
            paren_depth += 1
        elif char == ')' and quote_char is None:
            paren_depth -= 1
        elif char == '[' and quote_char is None:
            bracket_depth += 1
        elif char == ']' and quote_char is None:
            bracket_depth -= 1
        elif char == '{' and quote_char is None:
            brace_depth += 1
        elif char == '}' and quote_char is None:
            brace_depth -= 1
    
    return False

def _evaluate_param(param_str: str) -> Any:
    """
    尝试评估参数值
    """
    param_str = param_str.strip()
    
    # 处理三引号字符串
    if param_str.startswith('"""') and param_str.endswith('"""') and len(param_str) >= 6:
        return param_str[3:-3]
    elif param_str.startswith("'''") and param_str.endswith("'''") and len(param_str) >= 6:
        return param_str[3:-3]
    
    # 处理普通字符串
    if (param_str.startswith('"') and param_str.endswith('"')) or \
       (param_str.startswith("'") and param_str.endswith("'")):
        return param_str[1:-1]
    
    # 尝试解析数字
    try:
        if '.' in param_str:
            return float(param_str)
        else:
            return int(param_str)
    except ValueError:
        pass
    
    # 布尔值
    if param_str.lower() == 'true':
        return True
    elif param_str.lower() == 'false':
        return False
    elif param_str.lower() == 'none' or param_str.lower() == 'null':
        return None
    
    # 返回原字符串
    return param_str