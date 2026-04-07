"""密钥管理"""

from __future__ import annotations

import os


class ConfigError(Exception):
    """配置错误"""


class SecretManager:
    """密钥管理器 — 从环境变量安全读取 API Key"""

    @staticmethod
    def get_api_key(env_var: str) -> str:
        """从环境变量获取 API Key"""
        key = os.environ.get(env_var)
        if not key:
            raise ConfigError(f"Environment variable {env_var} not set")
        return key

    @staticmethod
    def mask_key(key: str) -> str:
        """脱敏显示"""
        if len(key) <= 8:
            return "****"
        return key[:4] + "****" + key[-4:]
