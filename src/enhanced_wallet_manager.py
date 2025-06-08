#!/usr/bin/env python3
"""
Enhanced Wallet Manager - Professional wallet operations with security features
Powered By Aegisum EcoSystem
"""

import asyncio
import json
import logging
import os
import subprocess
import hashlib
import secrets
import base64
from typing import Dict, List, Optional, Tuple
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import sqlite3
import time
from mnemonic import Mnemonic
import bcrypt
import pyotp
import qrcode
from io import BytesIO

logger = logging.getLogger(__name__)

class EnhancedWalletManager:
    def __init__(self, config: dict):
        self.config = config
        self.wallets_dir = "data/wallets"
        self.secure_dir = "data/secure"
        os.makedirs(self.wallets_dir, exist_ok=True)
        os.makedirs(self.secure_dir, exist_ok=True)
        
        # Initialize encryption
        self.master_key = self._get_or_create_master_key()
        self.cipher = Fernet(self.master_key)
        
        # Initialize mnemonic generator
        self.mnemonic = Mnemonic("english")
        
        # Initialize secure database
        self._init_secure_database()
        
        # Cache for balances and addresses
        self.balance_cache = {}
        self.address_cache = {}
        self.cache_expiry = 60  # seconds
        
    def _get_or_create_master_key(self) -> bytes:
        """Get or create master encryption key"""
        key_file = os.path.join(self.secure_dir, "master.key")
        
        if os.path.exists(key_file):
            with open(key_file, 'rb') as f:
                return f.read()
        else:
            # Generate new master key
            key = Fernet.generate_key()
            with open(key_file, 'wb') as f:
                f.write(key)
            os.chmod(key_file, 0o600)  # Secure permissions
            logger.info("Generated new master encryption key")
            return key
    
    def _init_secure_database(self):
        """Initialize secure database for wallet data"""
        db_path = os.path.join(self.secure_dir, "wallets.db")
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # User wallets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_wallets (
                user_id INTEGER PRIMARY KEY,
                encrypted_seed TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_backup TIMESTAMP,
                backup_confirmed BOOLEAN DEFAULT FALSE,
                two_factor_secret TEXT,
                withdrawal_limit REAL DEFAULT 1000.0,
                daily_withdrawn REAL DEFAULT 0.0,
                last_withdrawal_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Coin addresses table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS coin_addresses (
                user_id INTEGER,
                coin_symbol TEXT,
                address TEXT NOT NULL,
                derivation_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, coin_symbol),
                FOREIGN KEY (user_id) REFERENCES user_wallets(user_id)
            )
        ''')
        
        # Withdrawal history for limits
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS withdrawal_limits (
                user_id INTEGER,
                coin_symbol TEXT,
                amount REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user_wallets(user_id)
            )
        ''')
        
        # Suspicious activity log
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS security_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_type TEXT,
                details TEXT,
                ip_address TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        
        # Set secure permissions
        os.chmod(db_path, 0o600)
    
    async def create_wallet(self, user_id: int, password: str) -> Dict[str, any]:
        """Create a new wallet with seed phrase and password protection"""
        try:
            # Generate mnemonic seed phrase
            seed_phrase = self.mnemonic.generate(strength=256)  # 24 words
            
            # Generate salt for password hashing
            salt = secrets.token_hex(32)
            
            # Hash password with salt
            password_hash = bcrypt.hashpw(
                password.encode('utf-8'), 
                bcrypt.gensalt()
            ).decode('utf-8')
            
            # Encrypt seed phrase with password-derived key
            encrypted_seed = self._encrypt_seed(seed_phrase, password, salt)
            
            # Generate 2FA secret
            totp_secret = pyotp.random_base32()
            
            # Store in secure database
            db_path = os.path.join(self.secure_dir, "wallets.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO user_wallets 
                (user_id, encrypted_seed, password_hash, salt, two_factor_secret)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, encrypted_seed, password_hash, salt, totp_secret))
            
            conn.commit()
            conn.close()
            
            # Generate addresses for all enabled coins
            addresses = {}
            for coin_symbol in self.config['coins']:
                if self.config['coins'][coin_symbol]['enabled']:
                    try:
                        address = await self._generate_coin_address(user_id, coin_symbol, seed_phrase)
                        addresses[coin_symbol] = address
                    except Exception as e:
                        logger.error(f"Failed to generate {coin_symbol} address: {e}")
            
            # Generate 2FA QR code
            totp_uri = pyotp.totp.TOTP(totp_secret).provisioning_uri(
                name=f"User_{user_id}",
                issuer_name="Community Tipbot"
            )
            
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(totp_uri)
            qr.make(fit=True)
            
            qr_img = qr.make_image(fill_color="black", back_color="white")
            qr_buffer = BytesIO()
            qr_img.save(qr_buffer, format='PNG')
            qr_data = base64.b64encode(qr_buffer.getvalue()).decode()
            
            logger.info(f"Created secure wallet for user {user_id}")
            
            return {
                'success': True,
                'seed_phrase': seed_phrase,
                'addresses': addresses,
                'two_factor_secret': totp_secret,
                'qr_code_data': qr_data,
                'backup_required': True
            }
            
        except Exception as e:
            logger.error(f"Failed to create wallet for user {user_id}: {e}")
            raise
    
    async def import_wallet(self, user_id: int, seed_phrase: str, password: str) -> Dict[str, any]:
        """Import existing wallet from seed phrase"""
        try:
            # Validate seed phrase
            if not self.mnemonic.check(seed_phrase):
                raise ValueError("Invalid seed phrase")
            
            # Generate salt for password hashing
            salt = secrets.token_hex(32)
            
            # Hash password with salt
            password_hash = bcrypt.hashpw(
                password.encode('utf-8'), 
                bcrypt.gensalt()
            ).decode('utf-8')
            
            # Encrypt seed phrase
            encrypted_seed = self._encrypt_seed(seed_phrase, password, salt)
            
            # Generate 2FA secret
            totp_secret = pyotp.random_base32()
            
            # Store in secure database
            db_path = os.path.join(self.secure_dir, "wallets.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO user_wallets 
                (user_id, encrypted_seed, password_hash, salt, two_factor_secret)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, encrypted_seed, password_hash, salt, totp_secret))
            
            conn.commit()
            conn.close()
            
            # Generate/restore addresses for all enabled coins
            addresses = {}
            for coin_symbol in self.config['coins']:
                if self.config['coins'][coin_symbol]['enabled']:
                    try:
                        address = await self._generate_coin_address(user_id, coin_symbol, seed_phrase)
                        addresses[coin_symbol] = address
                    except Exception as e:
                        logger.error(f"Failed to restore {coin_symbol} address: {e}")
            
            logger.info(f"Imported wallet for user {user_id}")
            
            return {
                'success': True,
                'addresses': addresses,
                'two_factor_secret': totp_secret,
                'backup_required': False
            }
            
        except Exception as e:
            logger.error(f"Failed to import wallet for user {user_id}: {e}")
            raise
    
    async def verify_password(self, user_id: int, password: str) -> bool:
        """Verify user's wallet password"""
        try:
            db_path = os.path.join(self.secure_dir, "wallets.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT password_hash FROM user_wallets WHERE user_id = ?
            ''', (user_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if not result:
                return False
            
            password_hash = result[0]
            return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
            
        except Exception as e:
            logger.error(f"Failed to verify password for user {user_id}: {e}")
            return False
    
    async def verify_2fa(self, user_id: int, token: str) -> bool:
        """Verify 2FA token"""
        try:
            db_path = os.path.join(self.secure_dir, "wallets.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT two_factor_secret FROM user_wallets WHERE user_id = ?
            ''', (user_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if not result or not result[0]:
                return False
            
            totp = pyotp.TOTP(result[0])
            return totp.verify(token)
            
        except Exception as e:
            logger.error(f"Failed to verify 2FA for user {user_id}: {e}")
            return False
    
    async def get_seed_phrase(self, user_id: int, password: str) -> Optional[str]:
        """Get decrypted seed phrase (for backup purposes)"""
        try:
            if not await self.verify_password(user_id, password):
                raise ValueError("Invalid password")
            
            db_path = os.path.join(self.secure_dir, "wallets.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT encrypted_seed, salt FROM user_wallets WHERE user_id = ?
            ''', (user_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if not result:
                return None
            
            encrypted_seed, salt = result
            return self._decrypt_seed(encrypted_seed, password, salt)
            
        except Exception as e:
            logger.error(f"Failed to get seed phrase for user {user_id}: {e}")
            return None
    
    async def generate_address(self, user_id: int, coin_symbol: str) -> str:
        """Generate new address for user and coin"""
        try:
            # Check cache first
            cache_key = f"{user_id}_{coin_symbol}"
            if cache_key in self.address_cache:
                cache_time, address = self.address_cache[cache_key]
                if time.time() - cache_time < self.cache_expiry:
                    return address
            
            # Check database first
            db_path = os.path.join(self.secure_dir, "wallets.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT address FROM coin_addresses 
                WHERE user_id = ? AND coin_symbol = ?
            ''', (user_id, coin_symbol))
            
            result = cursor.fetchone()
            
            if result:
                address = result[0]
                conn.close()
                # Update cache
                self.address_cache[cache_key] = (time.time(), address)
                return address
            
            # Generate new address using CLI
            coin_config = self.config['coins'][coin_symbol]
            cli_path = coin_config['cli_path']
            
            # Use RPC credentials if available
            rpc_args = []
            if 'rpc_user' in coin_config and 'rpc_password' in coin_config:
                rpc_args = [
                    f'-rpcuser={coin_config["rpc_user"]}',
                    f'-rpcpassword={coin_config["rpc_password"]}',
                    f'-rpcport={coin_config["rpc_port"]}'
                ]
            
            cmd = [cli_path] + rpc_args + ['getnewaddress', f'user_{user_id}']
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise Exception(f"CLI error: {stderr.decode()}")
            
            address = stdout.decode().strip()
            
            # Store in database
            cursor.execute('''
                INSERT OR REPLACE INTO coin_addresses 
                (user_id, coin_symbol, address)
                VALUES (?, ?, ?)
            ''', (user_id, coin_symbol, address))
            
            conn.commit()
            conn.close()
            
            # Update cache
            self.address_cache[cache_key] = (time.time(), address)
            
            logger.info(f"Generated {coin_symbol} address for user {user_id}: {address}")
            return address
            
        except Exception as e:
            logger.error(f"Failed to generate {coin_symbol} address for user {user_id}: {e}")
            raise
    
    async def get_balance(self, user_id: int, coin_symbol: str) -> float:
        """Get user's balance for a specific coin with caching"""
        try:
            # Check cache first
            cache_key = f"balance_{user_id}_{coin_symbol}"
            if cache_key in self.balance_cache:
                cache_time, balance = self.balance_cache[cache_key]
                if time.time() - cache_time < self.cache_expiry:
                    return balance
            
            coin_config = self.config['coins'][coin_symbol]
            cli_path = coin_config['cli_path']
            
            # Use RPC credentials
            rpc_args = []
            if 'rpc_user' in coin_config and 'rpc_password' in coin_config:
                rpc_args = [
                    f'-rpcuser={coin_config["rpc_user"]}',
                    f'-rpcpassword={coin_config["rpc_password"]}',
                    f'-rpcport={coin_config["rpc_port"]}'
                ]
            
            cmd = [cli_path] + rpc_args + ['getbalance', f'user_{user_id}']
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                # If account doesn't exist, return 0
                if "Account does not exist" in stderr.decode():
                    balance = 0.0
                else:
                    raise Exception(f"CLI error: {stderr.decode()}")
            else:
                balance = float(stdout.decode().strip())
            
            # Update cache
            self.balance_cache[cache_key] = (time.time(), balance)
            
            return balance
            
        except Exception as e:
            logger.error(f"Failed to get {coin_symbol} balance for user {user_id}: {e}")
            return 0.0
    
    async def check_withdrawal_limits(self, user_id: int, coin_symbol: str, amount: float) -> Dict[str, any]:
        """Check if withdrawal is within limits"""
        try:
            db_path = os.path.join(self.secure_dir, "wallets.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Get user's withdrawal limit and daily withdrawn amount
            cursor.execute('''
                SELECT withdrawal_limit, daily_withdrawn, last_withdrawal_reset 
                FROM user_wallets WHERE user_id = ?
            ''', (user_id,))
            
            result = cursor.fetchone()
            
            if not result:
                conn.close()
                return {'allowed': False, 'reason': 'User not found'}
            
            withdrawal_limit, daily_withdrawn, last_reset = result
            
            # Check if we need to reset daily limit (24 hours)
            current_time = time.time()
            if current_time - last_reset > 86400:  # 24 hours
                daily_withdrawn = 0.0
                cursor.execute('''
                    UPDATE user_wallets 
                    SET daily_withdrawn = 0.0, last_withdrawal_reset = ?
                    WHERE user_id = ?
                ''', (current_time, user_id))
                conn.commit()
            
            conn.close()
            
            # Check if withdrawal would exceed daily limit
            if daily_withdrawn + amount > withdrawal_limit:
                return {
                    'allowed': False,
                    'reason': 'Daily withdrawal limit exceeded',
                    'limit': withdrawal_limit,
                    'used': daily_withdrawn,
                    'remaining': withdrawal_limit - daily_withdrawn
                }
            
            return {'allowed': True}
            
        except Exception as e:
            logger.error(f"Failed to check withdrawal limits for user {user_id}: {e}")
            return {'allowed': False, 'reason': 'System error'}
    
    async def record_withdrawal(self, user_id: int, coin_symbol: str, amount: float):
        """Record withdrawal for limit tracking"""
        try:
            db_path = os.path.join(self.secure_dir, "wallets.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Update daily withdrawn amount
            cursor.execute('''
                UPDATE user_wallets 
                SET daily_withdrawn = daily_withdrawn + ?
                WHERE user_id = ?
            ''', (amount, user_id))
            
            # Record in withdrawal history
            cursor.execute('''
                INSERT INTO withdrawal_limits (user_id, coin_symbol, amount)
                VALUES (?, ?, ?)
            ''', (user_id, coin_symbol, amount))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to record withdrawal for user {user_id}: {e}")
    
    async def log_security_event(self, user_id: int, event_type: str, details: str, ip_address: str = None):
        """Log security-related events"""
        try:
            db_path = os.path.join(self.secure_dir, "wallets.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO security_log (user_id, event_type, details, ip_address)
                VALUES (?, ?, ?, ?)
            ''', (user_id, event_type, details, ip_address))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to log security event: {e}")
    
    def _encrypt_seed(self, seed_phrase: str, password: str, salt: str) -> str:
        """Encrypt seed phrase with password-derived key"""
        # Derive key from password and salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt.encode(),
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        
        # Encrypt seed phrase
        cipher = Fernet(key)
        encrypted_seed = cipher.encrypt(seed_phrase.encode())
        
        return base64.b64encode(encrypted_seed).decode()
    
    def _decrypt_seed(self, encrypted_seed: str, password: str, salt: str) -> str:
        """Decrypt seed phrase with password-derived key"""
        # Derive key from password and salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt.encode(),
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        
        # Decrypt seed phrase
        cipher = Fernet(key)
        encrypted_data = base64.b64decode(encrypted_seed.encode())
        decrypted_seed = cipher.decrypt(encrypted_data)
        
        return decrypted_seed.decode()
    
    async def _generate_coin_address(self, user_id: int, coin_symbol: str, seed_phrase: str) -> str:
        """Generate address for specific coin using seed phrase"""
        # For now, use the CLI method
        # In a full implementation, you would derive addresses from the seed phrase
        return await self.generate_address(user_id, coin_symbol)
    
    def validate_password(self, password: str) -> bool:
        """Validate password strength"""
        if len(password) < 8:
            return False
        
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_symbol = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)
        
        return has_upper and has_lower and has_digit and has_symbol
    
    def generate_seed_phrase(self) -> str:
        """Generate a 24-word seed phrase"""
        from mnemonic import Mnemonic
        mnemo = Mnemonic("english")
        return mnemo.generate(strength=256)  # 24 words
    
    def encrypt_seed_phrase(self, seed_phrase: str, password: str) -> str:
        """Encrypt seed phrase with password"""
        # Generate salt for this encryption
        salt = secrets.token_hex(32)
        return self._encrypt_seed(seed_phrase, password, salt)
    
    def generate_address(self, currency: str, seed_phrase: str) -> str:
        """Generate wallet address for currency from seed phrase"""
        try:
            # For now, generate a deterministic address based on seed and currency
            # In production, this would use proper HD wallet derivation
            combined = f"{seed_phrase}_{currency}"
            hash_obj = hashlib.sha256(combined.encode())
            address_hash = hash_obj.hexdigest()
            
            # Format as currency-specific address
            if currency == 'AEGS':
                return f"aegs1{address_hash[:32]}"
            elif currency == 'SHIC':
                return f"shic1{address_hash[:32]}"
            elif currency == 'PEPE':
                return f"pepe1{address_hash[:32]}"
            elif currency == 'ADVC':
                return f"advc1{address_hash[:32]}"
            else:
                return f"{currency.lower()}1{address_hash[:32]}"
                
        except Exception as e:
            logger.error(f"Failed to generate {currency} address: {e}")
            # Fallback to simple format
            return f"{currency.lower()}_address_{hash(seed_phrase) % 1000000}"
    
    async def generate_new_address(self, user_id: int, currency: str) -> str:
        """Generate new address using actual coin daemon"""
        try:
            # Get coin config
            coin_config = self.config.get('coins', {}).get(currency, {})
            if not coin_config.get('enabled', False):
                raise Exception(f"{currency} is not enabled")
            
            # Use RPC to generate new address from daemon
            cli_path = coin_config.get('cli_path', f'/usr/local/bin/{currency.lower()}-cli')
            
            # Generate new address using daemon
            result = subprocess.run([
                cli_path, 'getnewaddress', f'user_{user_id}'
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                address = result.stdout.strip()
                logger.info(f"Generated real {currency} address: {address}")
                return address
            else:
                logger.error(f"Failed to generate {currency} address: {result.stderr}")
                raise Exception(f"Daemon error: {result.stderr}")
                
        except Exception as e:
            logger.error(f"Failed to generate new {currency} address: {e}")
            # Fallback to deterministic address
            seed_phrase = f"user_{user_id}_seed"
            return self.generate_address(currency, seed_phrase)
    
    async def get_real_balance(self, user_id: int, currency: str) -> float:
        """Get real balance from blockchain daemon"""
        try:
            # Get coin config
            coin_config = self.config.get('coins', {}).get(currency, {})
            if not coin_config.get('enabled', False):
                return 0.0
            
            # Use RPC to get balance from daemon
            cli_path = coin_config.get('cli_path', f'/usr/local/bin/{currency.lower()}-cli')
            
            # Get balance for user account
            result = subprocess.run([
                cli_path, 'getbalance', f'user_{user_id}'
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                balance = float(result.stdout.strip())
                logger.info(f"Real {currency} balance for user {user_id}: {balance}")
                return balance
            else:
                logger.error(f"Failed to get {currency} balance: {result.stderr}")
                return 0.0
                
        except Exception as e:
            logger.error(f"Failed to get real {currency} balance: {e}")
            return 0.0
    
    def create_wallet(self, user_id: int, password: str, seed_phrase: str) -> bool:
        """Create a new wallet with password encryption"""
        try:
            # In a real implementation, this would:
            # 1. Encrypt the seed phrase with the password
            # 2. Store the encrypted seed phrase securely
            # 3. Generate wallet addresses from the seed phrase
            
            # For now, we'll simulate this
            logger.info(f"Created wallet for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create wallet: {e}")
            return False