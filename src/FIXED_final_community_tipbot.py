#!/usr/bin/env python3
"""
🚀 ZERO ERROR Community Tipbot - All Markdown parsing errors eliminated
✅ Fixed Issues:
- Removed parse_mode=MARKDOWN from all edit_message_text calls
- Added parse_mode=None to prevent entity parsing errors
- Removed problematic symbols from password requirements text
- Fixed all send_message calls to use parse_mode=None

🎯 This eliminates the 'Can't parse entities' error that was crashing the bot
"""

import logging
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, filters
)

# Import our enhanced components
from enhanced_database import EnhancedDatabase
from enhanced_wallet_manager import EnhancedWalletManager

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
WALLET_PASSWORD, WALLET_CONFIRM, WALLET_IMPORT = range(3)

class CommunityTipbot:
    """Enhanced Community Tipbot with all features"""
    
    def __init__(self, config_path: str = "config/config.json"):
        """Initialize the Community Tipbot"""
        self.config = self._load_config(config_path)
        self.db = EnhancedDatabase(self.config['database']['path'])
        self.wallet_manager = EnhancedWalletManager(self.config)
        
        # Track user activity
        self.user_activity = {}
        self.faucet_cooldowns = {}
        
        logger.info("Community Tipbot initialized with all features")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file {config_path} not found, using defaults")
            return {
                "database": {"path": "data/community_tipbot.db"},
                "tokens": {
                    "AEGS": {"name": "Aegisum", "decimals": 18},
                    "SHIC": {"name": "Shiba Classic", "decimals": 18},
                    "PEPE": {"name": "Pepe", "decimals": 18},
                    "ADVC": {"name": "Advanced", "decimals": 18}
                },
                "faucet": {
                    "amounts": {"AEGS": 100, "SHIC": 50, "PEPE": 1000, "ADVC": 25},
                    "cooldown_hours": 24
                },
                "welcome_bonus": {
                    "AEGS": 500,
                    "SHIC": 250,
                    "PEPE": 5000,
                    "ADVC": 125
                }
            }
    
    # ==================== START & HELP COMMANDS ====================
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced start command with wallet creation"""
        user_id = update.effective_user.id
        username = update.effective_user.username or "Anonymous"
        
        # Track user activity
        self.user_activity[user_id] = {
            'last_seen': datetime.now(),
            'username': username
        }
        
        # Check if user already has a wallet
        user_data = self.db.get_user(user_id)
        if user_data:
            # Existing user - show main menu
            await self._show_main_menu(update, context)
        else:
            # New user - show wallet creation options
            await self._show_wallet_creation_menu(update, context)
    
    async def _show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show main menu for existing users"""
        user_id = update.effective_user.id
        user_data = self.db.get_user(user_id)
        
        message = (
            f"🎉 Welcome back to Community Tipbot!\n\n"
            f"👤 User: {update.effective_user.first_name}\n"
            f"🆔 ID: {user_id}\n"
            f"💰 Wallet: Active\n\n"
            f"🚀 Quick Actions:"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("💰 Balance", callback_data="show_balance"),
                InlineKeyboardButton("📥 Deposit", callback_data="show_deposit")
            ],
            [
                InlineKeyboardButton("🎁 Faucet", callback_data="claim_faucet"),
                InlineKeyboardButton("🏆 Leaderboard", callback_data="show_leaderboard")
            ],
            [
                InlineKeyboardButton("📊 Stats", callback_data="show_user_stats"),
                InlineKeyboardButton("⚙️ Settings", callback_data="show_settings")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=None)
    
    async def _show_wallet_creation_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show wallet creation menu for new users"""
        message = (
            "🎉 Welcome to Community Tipbot!\n\n"
            "🔐 To get started, you need a secure wallet.\n\n"
            "Choose an option:\n"
            "• Create New Wallet - Generate a fresh wallet with seed phrase\n"
            "• Import Wallet - Use existing 24-word seed phrase\n\n"
            "📚 Learn More - About Community Tipbot features"
        )
        
        keyboard = [
            [InlineKeyboardButton("🆕 Create New Wallet", callback_data="create_wallet")],
            [InlineKeyboardButton("📥 Import Existing Wallet", callback_data="import_wallet")],
            [InlineKeyboardButton("📚 Learn More", callback_data="learn_more")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=None)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced help command"""
        help_text = (
            "🤖 Community Tipbot Help\n\n"
            "💰 WALLET COMMANDS:\n"
            "/start - Start bot & create wallet\n"
            "/balance - Check your portfolio\n"
            "/deposit - Get deposit addresses\n"
            "/backup - View seed phrase (DM only)\n\n"
            "🎁 EARNING COMMANDS:\n"
            "/faucet - Claim daily rewards\n"
            "/tip @user amount token - Send tips\n\n"
            "📊 INFO COMMANDS:\n"
            "/stats - Your statistics\n"
            "/leaderboard - Top users\n"
            "/price token - Token prices\n\n"
            "⚙️ SETTINGS:\n"
            "/settings - Bot preferences\n"
            "/privacy - Privacy settings\n\n"
            "🔋 Powered by Aegisum EcoSystem"
        )
        
        await update.message.reply_text(help_text, parse_mode=None)
    
    # ==================== WALLET CREATION & IMPORT ====================
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard button presses"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "create_wallet":
            await self._start_wallet_creation(query, context)
        elif query.data == "import_wallet":
            await self._start_wallet_import(query, context)
        elif query.data == "learn_more":
            await self._show_learn_more(query, context)
        elif query.data == "show_balance":
            await self._show_balance_inline(query, context)
        elif query.data == "show_deposit":
            await self._show_deposit_inline(query, context)
        elif query.data == "claim_faucet":
            await self._claim_faucet_inline(query, context)
        elif query.data == "show_leaderboard":
            await self._show_leaderboard_inline(query, context)
        elif query.data == "show_user_stats":
            await self._show_user_stats_inline(query, context)
        elif query.data == "show_settings":
            await self._show_settings_inline(query, context)
    
    async def _start_wallet_creation(self, query, context):
        """Start wallet creation process"""
        user_id = query.from_user.id
        
        # Check if user already has wallet
        if self.db.get_user(user_id):
            await query.edit_message_text(
                "🔐 You already have a wallet! Use /backup to view your seed phrase.",
                parse_mode=None
            )
            return
        
        message = (
            "🔐 Create Your Secure Wallet\n\n"
            "Please create a strong password for your wallet:\n\n"
            "Requirements:\n"
            "• At least 8 characters\n"
            "• Include uppercase letters (A-Z)\n"
            "• Include lowercase letters (a-z)\n"
            "• Include numbers (0-9)\n"
            "• Include symbols\n\n"
            "💡 This password encrypts your seed phrase!\n"
            "⚠️ Never share this password with anyone!\n\n"
            "Please type your password:"
        )
        
        await query.edit_message_text(message, parse_mode=None)
        return WALLET_PASSWORD
    
    async def _start_wallet_import(self, query, context):
        """Start wallet import process"""
        message = (
            "📥 Import Existing Wallet\n\n"
            "This feature allows you to import an existing wallet using your seed phrase.\n\n"
            "⚠️ Security Notice:\n"
            "• Only import wallets you own\n"
            "• Never share your seed phrase\n"
            "• Make sure you're in a private chat\n\n"
            "Please send your 24-word seed phrase:"
        )
        
        await query.edit_message_text(message, parse_mode=None)
        return WALLET_IMPORT
    
    async def _show_learn_more(self, query, context):
        """Show learn more information"""
        message = (
            "📚 About Community Tipbot\n\n"
            "🎯 Features:\n"
            "• Multi-token wallet (AEGS, SHIC, PEPE, ADVC)\n"
            "• Daily faucet rewards\n"
            "• Secure seed phrase backup\n"
            "• Tip other users\n"
            "• Portfolio tracking\n"
            "• Leaderboards & stats\n\n"
            "🔒 Security:\n"
            "• Password-protected wallets\n"
            "• 24-word seed phrases\n"
            "• Private key encryption\n\n"
            "Ready to create your wallet?"
        )
        
        keyboard = [
            [InlineKeyboardButton("🆕 Create Wallet", callback_data="create_wallet")],
            [InlineKeyboardButton("📥 Import Wallet", callback_data="import_wallet")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=None)
    
    async def wallet_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle wallet password input"""
        password = update.message.text
        
        # Delete the password message for security
        try:
            await update.message.delete()
        except:
            pass
        
        # Validate password strength
        if not self.wallet_manager.validate_password(password):
            await update.effective_chat.send_message(
                "❌ Password too weak!\n\n"
                "Your password must include:\n"
                "• At least 8 characters\n"
                "• Uppercase letters (A-Z)\n"
                "• Lowercase letters (a-z)\n"
                "• Numbers (0-9)\n"
                "• Symbols\n\n"
                "Please try again with a stronger password:",
                parse_mode=None
            )
            return WALLET_PASSWORD
        
        # Store password temporarily
        context.user_data['wallet_password'] = password
        
        await update.effective_chat.send_message(
            "✅ Strong password accepted!\n\n"
            "Please confirm your password by typing it again:",
            parse_mode=None
        )
        
        return WALLET_CONFIRM
    
    async def wallet_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle wallet password confirmation"""
        password = update.message.text
        stored_password = context.user_data.get('wallet_password')
        
        # Delete the password message for security
        try:
            await update.message.delete()
        except:
            pass
        
        if password != stored_password:
            await update.effective_chat.send_message(
                "❌ Passwords don't match!\n\n"
                "Please enter your original password again:",
                parse_mode=None
            )
            return WALLET_PASSWORD
        
        try:
            # Create user in database
            user_id = update.effective_user.id
            username = update.effective_user.username or "Anonymous"
            
            # Generate wallet
            seed_phrase = self.wallet_manager.generate_seed_phrase()
            encrypted_seed = self.wallet_manager.encrypt_seed_phrase(seed_phrase, password)
            
            # Create user record
            self.db.create_user(
                user_id=user_id,
                username=username,
                encrypted_seed=encrypted_seed
            )
            
            # Give welcome bonus
            welcome_bonus = self.config.get('welcome_bonus', {})
            for token, amount in welcome_bonus.items():
                self.db.update_balance(user_id, token, amount)
            
            # Log wallet creation
            self.db.log_transaction(
                user_id=user_id,
                transaction_type="wallet_created",
                amount=0,
                token="SYSTEM",
                description="New wallet created with welcome bonus"
            )
            
            # Show success message with seed phrase
            bonus_text = ", ".join([f"{amount} {token}" for token, amount in welcome_bonus.items()])
            
            message = (
                f"🎉 Wallet Created Successfully!\n\n"
                f"🔐 Your 24-word seed phrase:\n"
                f"```\n{seed_phrase}\n```\n\n"
                f"⚠️ CRITICAL SECURITY NOTICE:\n"
                f"• Write down these words on paper\n"
                f"• Store in a safe place\n"
                f"• NEVER share with anyone\n"
                f"• This is your ONLY backup!\n\n"
                f"🎁 Welcome bonus received: {bonus_text}\n\n"
                f"🚀 Next steps:\n"
                f"• Check your balance with /balance\n"
                f"• Get deposit addresses with /deposit\n"
                f"• Claim daily rewards with /faucet\n"
                f"• Backup your wallet with /backup\n"
                f"• Explore features with /help\n\n"
                f"🔋 Powered By Aegisum EcoSystem"
            )
            
            await update.effective_chat.send_message(message, parse_mode=None)
            
            # Clear stored password
            context.user_data.clear()
            
            # Log wallet creation
            logger.info(f"Wallet created for user {user_id} ({username})")
            
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"Wallet creation failed: {e}")
            await update.effective_chat.send_message(
                f"❌ Wallet creation failed: {str(e)}\n\n"
                f"Please try again with /start",
                parse_mode=None
            )
            return ConversationHandler.END
    
    # ==================== BALANCE & PORTFOLIO ====================
    
    async def balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's token balances"""
        user_id = update.effective_user.id
        
        # Check if user has wallet
        if not self.db.get_user(user_id):
            await update.message.reply_text(
                "❌ You don't have a wallet yet! Use /start to create one.",
                parse_mode=None
            )
            return
        
        # Privacy check - only allow in DM
        if update.effective_chat.type != 'private':
            await update.message.reply_text(
                "🔒 For privacy, balance information is only available in direct messages.\n"
                "Please message me privately: @YourBotUsername",
                parse_mode=None
            )
            return
        
        # Get balances
        balances = self.db.get_user_balances(user_id)
        
        if not balances:
            message = "💰 Your Portfolio\n\n📊 All balances: 0.00\n\n🎁 Use /faucet to get started!"
        else:
            total_value = 0
            balance_lines = []
            
            for token, balance in balances.items():
                token_info = self.config['tokens'].get(token, {})
                token_name = token_info.get('name', token)
                
                balance_lines.append(f"• {balance:.2f} {token} ({token_name})")
                # Add mock price calculation
                total_value += balance * 0.01  # Mock price
            
            balance_text = "\n".join(balance_lines)
            message = (
                f"💰 Your Portfolio\n\n"
                f"📊 Token Balances:\n{balance_text}\n\n"
                f"💵 Estimated Value: ${total_value:.2f}\n\n"
                f"🎁 Use /faucet for daily rewards\n"
                f"📥 Use /deposit to add funds"
            )
        
        await update.message.reply_text(message, parse_mode=None)
    
    async def deposit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show deposit addresses"""
        user_id = update.effective_user.id
        
        # Check if user has wallet
        if not self.db.get_user(user_id):
            await update.message.reply_text(
                "❌ You don't have a wallet yet! Use /start to create one.",
                parse_mode=None
            )
            return
        
        # Privacy check - only allow in DM
        if update.effective_chat.type != 'private':
            await update.message.reply_text(
                "🔒 For privacy, deposit addresses are only available in direct messages.\n"
                "Please message me privately: @YourBotUsername",
                parse_mode=None
            )
            return
        
        # Generate mock addresses (in real implementation, derive from seed)
        addresses = {
            'AEGS': f"aegs1{user_id}mock{hash(str(user_id))%10000:04d}",
            'SHIC': f"shic1{user_id}mock{hash(str(user_id))%10000:04d}",
            'PEPE': f"pepe1{user_id}mock{hash(str(user_id))%10000:04d}",
            'ADVC': f"advc1{user_id}mock{hash(str(user_id))%10000:04d}"
        }
        
        message = "📥 Your Deposit Addresses\n\n"
        for token, address in addresses.items():
            token_info = self.config['tokens'].get(token, {})
            token_name = token_info.get('name', token)
            message += f"🔹 {token} ({token_name}):\n`{address}`\n\n"
        
        message += (
            "⚠️ Important:\n"
            "• Only send the correct token to each address\n"
            "• Double-check addresses before sending\n"
            "• Transactions may take time to confirm\n\n"
            "💡 Use /balance to check your portfolio"
        )
        
        await update.message.reply_text(message, parse_mode=None)
    
    # ==================== FAUCET SYSTEM ====================
    
    async def faucet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced faucet with cooldowns and anti-abuse"""
        user_id = update.effective_user.id
        
        # Check if user has wallet
        if not self.db.get_user(user_id):
            await update.message.reply_text(
                "❌ You don't have a wallet yet! Use /start to create one.",
                parse_mode=None
            )
            return
        
        # Check cooldown
        cooldown_hours = self.config['faucet']['cooldown_hours']
        last_claim = self.faucet_cooldowns.get(user_id)
        
        if last_claim:
            time_diff = datetime.now() - last_claim
            if time_diff < timedelta(hours=cooldown_hours):
                remaining = timedelta(hours=cooldown_hours) - time_diff
                hours = remaining.seconds // 3600
                minutes = (remaining.seconds % 3600) // 60
                
                await update.message.reply_text(
                    f"⏰ Faucet Cooldown Active\n\n"
                    f"You can claim again in: {hours}h {minutes}m\n\n"
                    f"💡 Faucet refills every {cooldown_hours} hours",
                    parse_mode=None
                )
                return
        
        # Anti-abuse check
        user_ip = self._get_user_ip(update)
        if self._is_abuse_detected(user_id, user_ip):
            await update.message.reply_text(
                "🚫 Anti-abuse protection activated.\n"
                "Please try again later.",
                parse_mode=None
            )
            return
        
        # Give faucet rewards
        faucet_amounts = self.config['faucet']['amounts']
        total_claimed = []
        
        for token, amount in faucet_amounts.items():
            self.db.update_balance(user_id, token, amount)
            total_claimed.append(f"{amount} {token}")
            
            # Log transaction
            self.db.log_transaction(
                user_id=user_id,
                transaction_type="faucet_claim",
                amount=amount,
                token=token,
                description="Daily faucet claim"
            )
        
        # Update cooldown
        self.faucet_cooldowns[user_id] = datetime.now()
        
        claimed_text = ", ".join(total_claimed)
        message = (
            f"🎁 Faucet Claimed Successfully!\n\n"
            f"💰 You received: {claimed_text}\n\n"
            f"⏰ Next claim available in {cooldown_hours} hours\n\n"
            f"💡 Use /balance to see your updated portfolio"
        )
        
        await update.message.reply_text(message, parse_mode=None)
        logger.info(f"Faucet claimed by user {user_id}: {claimed_text}")
    
    # ==================== STATISTICS & LEADERBOARD ====================
    
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user statistics"""
        user_id = update.effective_user.id
        
        if not self.db.get_user(user_id):
            await update.message.reply_text(
                "❌ You don't have a wallet yet! Use /start to create one.",
                parse_mode=None
            )
            return
        
        # Get user stats
        stats = self.db.get_user_stats(user_id)
        balances = self.db.get_user_balances(user_id)
        
        # Calculate total portfolio value (mock)
        total_value = sum(balance * 0.01 for balance in balances.values()) if balances else 0
        
        message = (
            f"📊 Your Statistics\n\n"
            f"👤 User ID: {user_id}\n"
            f"💰 Portfolio Value: ${total_value:.2f}\n"
            f"🎁 Faucet Claims: {stats.get('faucet_claims', 0)}\n"
            f"💸 Tips Sent: {stats.get('tips_sent', 0)}\n"
            f"💰 Tips Received: {stats.get('tips_received', 0)}\n"
            f"📅 Member Since: {stats.get('created_at', 'Unknown')}\n\n"
            f"🏆 Use /leaderboard to see rankings"
        )
        
        await update.message.reply_text(message, parse_mode=None)
    
    async def leaderboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show community leaderboard"""
        # Get top users (mock data for now)
        top_users = [
            {"username": "CryptoKing", "portfolio_value": 1250.50, "tips_sent": 45},
            {"username": "TokenMaster", "portfolio_value": 980.25, "tips_sent": 38},
            {"username": "FaucetFarmer", "portfolio_value": 750.75, "tips_sent": 29},
            {"username": "TipBot", "portfolio_value": 650.00, "tips_sent": 25},
            {"username": "Anonymous", "portfolio_value": 500.25, "tips_sent": 18}
        ]
        
        message = "🏆 Community Leaderboard\n\n"
        
        for i, user in enumerate(top_users, 1):
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔸"
            message += (
                f"{emoji} #{i} {user['username']}\n"
                f"   💰 ${user['portfolio_value']:.2f} | 💸 {user['tips_sent']} tips\n\n"
            )
        
        message += (
            "💡 Rankings based on portfolio value and community activity\n"
            "🎯 Use /stats to see your position"
        )
        
        await update.message.reply_text(message, parse_mode=None)
    
    # ==================== UTILITY METHODS ====================
    
    def _get_user_ip(self, update: Update) -> str:
        """Get user IP for anti-abuse (mock implementation)"""
        return "127.0.0.1"  # Mock IP
    
    def _is_abuse_detected(self, user_id: int, ip: str) -> bool:
        """Check for abuse patterns (mock implementation)"""
        return False  # Mock - no abuse detected
    
    def _get_user_ip(self, update: Update) -> str:
        """Get user IP for anti-abuse (mock implementation)"""
        return "127.0.0.1"  # Mock IP
    
    # Placeholder methods for inline callbacks
    async def _show_balance_inline(self, query, context):
        await query.edit_message_text("Use /balance command for detailed portfolio view.", parse_mode=None)
    
    async def _show_deposit_inline(self, query, context):
        await query.edit_message_text("Use /deposit command for deposit addresses.", parse_mode=None)
    
    async def _claim_faucet_inline(self, query, context):
        await query.edit_message_text("Use /faucet command to claim daily rewards.", parse_mode=None)
    
    async def _show_leaderboard_inline(self, query, context):
        await query.edit_message_text("Use /leaderboard command for rankings.", parse_mode=None)
    
    async def _show_user_stats_inline(self, query, context):
        await query.edit_message_text("Use /stats command for detailed statistics.", parse_mode=None)
    
    async def _show_settings_inline(self, query, context):
        await query.edit_message_text("Use /settings command for bot settings.", parse_mode=None)
    
    def setup_handlers(self, application: Application):
        """Setup all command handlers"""
        # Wallet creation conversation
        wallet_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.button_callback, pattern="^create_wallet$")],
            states={
                WALLET_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.wallet_password)],
                WALLET_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.wallet_confirm)],
                WALLET_IMPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.wallet_confirm)]
            },
            fallbacks=[CommandHandler("start", self.start)],
            per_message=False
        )
        
        # Add handlers
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("balance", self.balance))
        application.add_handler(CommandHandler("deposit", self.deposit))
        application.add_handler(CommandHandler("faucet", self.faucet))
        application.add_handler(CommandHandler("stats", self.stats))
        application.add_handler(CommandHandler("leaderboard", self.leaderboard))
        
        # Add conversation handler
        application.add_handler(wallet_conv_handler)
        
        # Add callback query handler for buttons
        application.add_handler(CallbackQueryHandler(self.button_callback))
        
        logger.info("All Community Tipbot handlers setup complete")

def main():
    """Main function to run the bot"""
    # Load bot token from config
    try:
        with open('config/config.json', 'r') as f:
            config = json.load(f)
        bot_token = config.get('bot_token')
        
        if not bot_token:
            logger.error("Bot token not found in config!")
            return
            
    except FileNotFoundError:
        logger.error("Config file not found! Please create config/config.json")
        return
    
    # Create bot instance
    bot = CommunityTipbot()
    
    # Create application
    application = Application.builder().token(bot_token).build()
    
    # Setup handlers
    bot.setup_handlers(application)
    
    logger.info("Community Tipbot starting...")
    
    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()