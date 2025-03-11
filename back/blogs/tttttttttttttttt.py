import os

# 获取当前脚本的目录
current_dir = os.path.dirname(__file__)

# 拼接相对路径
relative_path = os.path.join(current_dir, "data", "file.txt")

# 转换为绝对路径
abs_path = os.path.abspath(relative_path)

print("相对路径:", relative_path)
print("绝对路径:", abs_path)