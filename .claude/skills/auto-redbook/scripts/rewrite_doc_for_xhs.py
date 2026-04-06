#!/usr/bin/env python3
"""
小红书文档改写脚本

将原始文档改写为小红书风格的内容，包含：
1. Unicode灰色实线分割线（━━━━━━━━━━━━━━━）
2. 底部署名（by gegeewu）

用法：
  python3 rewrite_doc_for_xhs.py input.md [output.md]

参数：
  input.md    原始文档路径
  output.md   输出文件路径（默认：input_xhs.md）
"""

import sys
import os
from pathlib import Path

# 添加父目录到路径以导入 prompts_storytelling
sys.path.insert(0, str(Path(__file__).parent.parent))
from prompts_storytelling import (
    STYLE_CLASSIFIER_TEMPLATE,
    TECH_DOC_TEMPLATE,
    INTERVIEW_TEMPLATE,
    PRODUCT_TEMPLATE,
    PHILOSOPHY_TEMPLATE,
    TEMPLATE_MAP
)


def classify_document_style(document: str) -> str:
    """
    分析文档风格并返回标签
    返回: 'tech' | 'interview' | 'product' | 'philosophy' | 'philosophy'
    """
    # 简单的关键词匹配分类
    tech_keywords = ['架构', '系统', 'API', '性能', '算法', '代码', '框架', '数据库', '缓存', '优化']
    interview_keywords = ['访谈', '对话', '他说', '我认为', '观点', '分享', '讨论', '问答']
    product_keywords = ['推荐', '工具', '好用', '体验', '使用', '简单', '方便', 'App', '软件']
    philosophy_keywords = ['孤独', '原子化', '隐喻', '存在', '尼采', '卡夫卡', '荒诞', '异化', '哲学',
                           '银翼杀手', '灵魂', '命运', '意识', '虚无', '结构', '悬在', '深渊']
    
    doc_lower = document.lower()
    
    tech_score = sum(1 for kw in tech_keywords if kw in doc_lower)
    interview_score = sum(1 for kw in interview_keywords if kw in doc_lower)
    product_score = sum(1 for kw in product_keywords if kw in doc_lower)
    philosophy_score = sum(1 for kw in philosophy_keywords if kw in doc_lower)
    
    scores = {'tech': tech_score, 'interview': interview_score,
              'product': product_score, 'philosophy': philosophy_score}
    return max(scores, key=scores.get) if max(scores.values()) > 0 else 'tech'


def add_signature_if_missing(content: str) -> str:
    """
    在文档底部添加署名（如果不存在）
    署名格式：\n\nby gegeewu 🦉
    """
    signature = "by gegeewu 🦉"
    if signature not in content:
        # 在文档末尾添加署名
        content = content.rstrip() + f"\n\n{signature}"
    return content


def get_rewrite_prompt(document: str, style: str = None) -> str:
    """
    根据文档风格获取对应的改写prompt
    
    参数：
      document: 原始文档内容
      style: 文档风格（'tech'|'interview'|'product'|'philosophy'），None则自动分类
    
    返回：
      完整的改写prompt
    """
    if style is None:
        style = classify_document_style(document)
    
    # 获取对应模板
    if style == 'interview':
        template = INTERVIEW_TEMPLATE
    elif style == 'product':
        template = PRODUCT_TEMPLATE
    elif style == 'philosophy':
        template = PHILOSOPHY_TEMPLATE
    else:  # tech or default
        template = TECH_DOC_TEMPLATE
    
    # 填充文档内容
    prompt = template.format(document=document)
    return prompt


def rewrite_document(input_file: str, output_file: str = None) -> str:
    """
    读取原始文档并返回改写用的prompt（供AI使用）
    
    实际改写由AI完成，此函数返回prompt和元数据
    
    返回：
      dict: {
        'style': 文档风格,
        'prompt': 完整的改写prompt,
        'input_file': 输入文件路径,
        'output_file': 输出文件路径
      }
    """
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_file}")
    
    # 读取原始文档
    with open(input_path, 'r', encoding='utf-8') as f:
        document = f.read()
    
    # 自动分类风格
    style = classify_document_style(document)
    
    # 生成改写prompt
    prompt = get_rewrite_prompt(document, style)
    
    # 确定输出文件路径
    if output_file is None:
        output_path = input_path.with_suffix('').with_suffix('').with_name(
            input_path.stem + "_xhs" + input_path.suffix
        )
    else:
        output_path = Path(output_file)
    
    return {
        'style': style,
        'prompt': prompt,
        'input_file': str(input_path),
        'output_file': str(output_path)
    }


def post_process_content(content: str) -> str:
    """
    后处理改写后的内容：
    1. 确保使用Unicode实线分割线（替换任何其他形式的分割线）
    2. 确保底部署名存在
    
    参数：
      content: AI改写后的内容
    
    返回：
      处理后的小红书文案
    """
    # 1. 统一分割线为Unicode灰色实线（U+2501）
    # 替换各种可能的分割线格式
    import re
    
    # 替换短横线风格的分割线（至少10个连续短横线）
    content = re.sub(r'-{10,}', '━━━━━━━━━━━━━━━', content)
    
    # 替换等号风格的分割线
    content = re.sub(r'={10,}', '━━━━━━━━━━━━━━━', content)
    
    # 替换其他常见的分隔符组合
    content = re.sub(r'─{10,}', '━━━━━━━━━━━━━━━', content)  # 已经是细线，保持
    content = re.sub(r'━{10,}', '━━━━━━━━━━━━━━━', content)  # 已经是粗线，保持
    
    # 2. 确保署名在文档最底部
    content = add_signature_if_missing(content)
    
    # 3. 添加底部署名
    if not content.strip().endswith('by gegeewu 🦉'):
        content = content.rstrip() + '\n\nby gegeewu 🦉\n'
    
    return content


def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        result = rewrite_document(input_file, output_file)
        
        print(f"📄 输入文件: {result['input_file']}")
        print(f"📄 输出文件: {result['output_file']}")
        print(f"🏷️  文档风格: {result['style']}")
        print(f"\n📝 改写Prompt已生成，请使用AI进行改写")
        print(f"   建议输出文件: {result['output_file']}")
        
        # 可选：将prompt保存到文件供调试
        prompt_file = Path(result['output_file']).with_suffix('.prompt.txt')
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(result['prompt'])
        print(f"   Prompt已保存: {prompt_file}")
        
    except FileNotFoundError as e:
        print(f"❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
