# 贡献指南

感谢你对 OKX AI 交易机器人项目的关注！我们欢迎各种形式的贡献。

## 🤝 如何贡献

### 报告问题

- 使用 [GitHub Issues](https://github.com/miaoyuhan/ai_agent_full/issues) 报告 bug
- 提供详细的问题描述、复现步骤和环境信息
- 添加相关标签（bug、enhancement、question等）

### 提交功能

1. **Fork 仓库**
2. **创建特性分支**：`git checkout -b feature/amazing-feature`
3. **提交更改**：`git commit -m 'Add some amazing feature'`
4. **推送分支**：`git push origin feature/amazing-feature`
5. **创建 Pull Request**

### 代码规范

#### Python 代码风格

- 遵循 PEP 8 规范
- 使用 4 空格缩进，不使用 Tab
- 行长度限制为 120 字符
- 使用有意义的变量和函数命名

#### 注释和文档

- 所有公共函数必须包含文档字符串
- 使用中文注释解释复杂逻辑
- 更新相关文档

```python
def example_function(param1: str, param2: int = 0) -> bool:
    """
    示例函数说明
    
    Args:
        param1: 参数1说明
        param2: 参数2说明，默认为0
        
    Returns:
        bool: 返回值说明
        
    Raises:
        ValueError: 当参数不合法时抛出
    """
    return True
```

#### 类型注解

- 使用类型注解提高代码可读性
- 导入 `typing` 模块中的类型

### 测试要求

- 新功能必须包含测试
- 确保所有测试通过
- 测试覆盖率不低于 80%

```bash
# 运行测试
python -m pytest tests/

# 检查覆盖率
python -m pytest --cov=okx_trade_agent tests/
```

### 提交信息规范

使用语义化提交信息：

```
<type>(<scope>): <subject>

<body>

<footer>
```

**类型**：
- `feat`: 新功能
- `fix`: 修复bug
- `docs`: 文档更新
- `style`: 代码格式调整
- `refactor`: 重构
- `test`: 测试相关
- `chore`: 构建工具或辅助工具的变动

**示例**：
```
feat(trading): 添加止损止盈功能

- 实现 TP/SL 算法单
- 添加风险检查机制
- 更新相关文档

Closes #123
```

## 🐛 Bug 报告

使用以下模板报告 bug：

```markdown
**Bug 描述**
简要描述 bug

**复现步骤**
1. 执行命令...
2. 点击...
3. 查看错误...

**期望行为**
描述你期望发生的情况

**实际行为**
描述实际发生的情况

**环境信息**
- OS: [e.g. macOS 14.0]
- Python 版本: [e.g. 3.9.0]
- 依赖版本: [e.g. ccxt 4.0.0]

**附加信息**
- 错误日志
- 相关截图
```

## 💡 功能建议

使用以下模板建议新功能：

```markdown
**功能描述**
简要描述建议的功能

**使用场景**
描述这个功能的使用场景和价值

**实现方案**
如果有的话，提供实现思路

**替代方案**
考虑过的其他实现方式
```

## 📝 开发环境设置

### 本地开发

1. **克隆仓库**
```bash
git clone https://github.com/miaoyuhan/ai_agent_full.git
cd ai_agent_full
```

2. **创建虚拟环境**
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
```

3. **安装开发依赖**
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt  # 如果有的话
```

4. **安装 pre-commit hooks**
```bash
pre-commit install
```

### 代码质量工具

项目使用以下工具保证代码质量：

- **Black**: 代码格式化
- **Flake8**: 代码检查
- **mypy**: 类型检查
- **isort**: 导入排序

运行所有检查：
```bash
black .
flake8 .
mypy .
isort .
```

## 🎯 发布流程

### 版本管理

项目使用 [语义化版本](https://semver.org/)：

- `MAJOR.MINOR.PATCH`
- `MAJOR`: 不兼容的API更改
- `MINOR`: 向后兼容的功能新增
- `PATCH`: 向后兼容的bug修复

### 发布检查清单

- [ ] 所有测试通过
- [ ] 文档已更新
- [ ] CHANGELOG.md 已更新
- [ ] 版本号已更新
- [ ] 创建 Git tag

## 🏷️ 标签和分类

### GitHub Labels

- `bug`: Bug修复
- `enhancement`: 功能增强
- `good first issue`: 适合新手的问题
- `help wanted`: 需要帮助
- `documentation`: 文档相关
- `question`: 问题咨询

### 代码审查

所有 PR 都需要代码审查：

1. **自动化检查通过**
2. **至少一人审查批准**
3. **讨论已解决**
4. **无冲突可合并**

## 📄 许可证

贡献代码意味着你同意将代码以 MIT 许可证授权给项目。

## 🙏 致谢

感谢所有为项目做出贡献的开发者！

## 📞 联系方式

- 项目主页: https://github.com/miaoyuhan/ai_agent_full
- Issues: https://github.com/miaoyuhan/ai_agent_full/issues
- Discussions: https://github.com/miaoyuhan/ai_agent_full/discussions

---

再次感谢你的贡献！每一个贡献都让这个项目变得更好。