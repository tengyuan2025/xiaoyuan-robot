# -*- coding: utf-8 -*-
"""日志配置模块"""

import logging
import os
import sys
from typing import Optional


_logger: Optional[logging.Logger] = None


def setup_logger(
    name: str = "robot",
    level: str = "INFO",
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    设置日志记录器

    Args:
        name: 日志记录器名称
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 日志文件路径（可选）

    Returns:
        配置好的日志记录器
    """
    global _logger

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 清除已有的处理器
    logger.handlers.clear()

    # 控制台输出格式
    console_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )

    # 文件输出格式（更详细）
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 添加控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 添加文件处理器（如果指定了日志文件）
    if log_file:
        try:
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"无法创建日志文件 {log_file}: {e}")

    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    """获取全局日志记录器"""
    global _logger
    if _logger is None:
        _logger = setup_logger()
    return _logger
