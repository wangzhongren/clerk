import inspect
import ast
from typing import Dict, List, Callable, Any, Optional
from bs4 import BeautifulSoup

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

# 全局注册表实例
global_registry = FunctionRegistry()

def _split_parameters(args_text: str) -> List[str]:
    """分割参数字符串，处理嵌套的引号和括号"""
    parts = []
    current = ""
    quote_char = None
    paren_depth = 0
    
    for char in args_text:
        if char in ['"', "'"] and quote_char is None:
            quote_char = char
            current += char
        elif char == quote_char:
            quote_char = None
            current += char
        elif char == '(' and quote_char is None:
            paren_depth += 1
            current += char
        elif char == ')' and quote_char is None and paren_depth > 0:
            paren_depth -= 1
            current += char
        elif char == ',' and quote_char is None and paren_depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += char
    
    if current.strip():
        parts.append(current.strip())
    
    return parts

def _parse_value(value_str: str) -> Any:
    """解析参数值"""
    value_str = value_str.strip()
    
    # 字符串
    if (value_str.startswith('"') and value_str.endswith('"')) or \
       (value_str.startswith("'") and value_str.endswith("'")):
        return value_str[1:-1]
    
    # 数字
    try:
        if '.' in value_str:
            return float(value_str)
        else:
            return int(value_str)
    except ValueError:
        pass
    
    # 布尔值
    if value_str.lower() == 'true':
        return True
    elif value_str.lower() == 'false':
        return False
    
    # None值
    if value_str.lower() == 'none' or value_str.lower() == 'null':
        return None
    
    # 其他情况返回原字符串
    return value_str

def _parse_ast_value(node: ast.expr) -> Any:
    """递归地将 AST 节点转换为 Python 对象"""
    if isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.Str): # 兼容 Python < 3.8
        return node.s
    elif isinstance(node, ast.Num): # 兼容 Python < 3.8
        return node.n
    elif isinstance(node, ast.Name):
        # 如果参数是变量名而非字面量，返回其名称字符串（视需求而定，这里返回 None 或抛出异常也可）
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
    else:
        # 对于无法解析的复杂表达式（如函数调用作为参数），返回原始源码或 None
        return None

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
        
        # 清理可能存在的周围空白，但不要过度修改内部格式，因为 ast 需要准确的缩进/换行
        code_block = raw_content.strip()
        
        if not code_block:
            continue
            
        # 关键修复点：
        # 原来的逻辑是按 ';' 分割，这很不安全。
        # 现在的策略：将整个块视为一个 Python 脚本片段进行 ast 解析。
        # 为了支持多个连续的函数调用（如 func1(); func2()），我们需要确保它们是合法的语句。
        
        try:
            # ast.parse 需要一个完整的模块。如果用户提供的只是表达式列表而没有分号结尾，
            # 或者有多行字符串，ast.parse 通常能很好地处理，只要语法合法。
            # 如果原始文本中用分号分隔多个调用，ast 也能识别为多个 Expr 节点。
            
            tree = ast.parse(code_block)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                    call_node = node.value
                    
                    func_name = ""
                    # 处理简单的名字 func() 或属性访问 obj.func()
                    if isinstance(call_node.func, ast.Name):
                        func_name = call_node.func.id
                    elif isinstance(call_node.func, ast.Attribute):
                        # 如果是 obj.method()，我们可能需要拼接，这里简单取 attr
                        func_name = call_node.func.attr 
                    
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
                    
        except SyntaxError as e:
            # 如果 ast 解析失败，说明文本不是合法的 Python 调用语法
            # 可以选择记录日志或跳过，而不是像原来那样产生错误的部分解析结果
            print(f"警告：无法解析函数调用块，语法错误：{e}")
            print(f"问题内容片段：{code_block[:100]}...")
            continue
        except Exception as e:
            print(f"解析过程中发生未知错误：{e}")
            continue

    return all_calls