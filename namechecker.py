import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import string

# Define the allowed character sets for names
BASE_ALLOWED_CHARS = string.ascii_letters + string.digits + """!"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"""
USERNAME_ALLOWED_CHAR_SET = set(BASE_ALLOWED_CHARS) # For global usernames
NICK_OR_GLOBAL_NAME_ALLOWED_CHAR_SET = set(BASE_ALLOWED_CHARS + " ") # For server nicks and global display names

class NameChecker(commands.Cog):
    """
    Checks user profiles against server criteria:
    - Name/Nickname/Global Display Name: character compliance & prohibited words.
    - Profile Customization: Ensures a server nick or global display name is set.
    - Bio ("About Me"): Checks for prohibited words (via command).
    """

    CONFIG_IDENTIFIER = "profilechecker_cog_V7_WordFilter"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=self.CONFIG_IDENTIFIER,
            force_registration=True
        )
        default_guild = {
            "alert_channel": None,
            "prohibited_bio_words": [], # Shared list for names and bios for now
        }
        self.config.register_guild(**default_guild)

    def _format_found_list(self, found_items: list[str]) -> str:
        """Helper to format a list of found prohibited words or invalid characters."""
        if not found_items:
            return "None"
        return ", ".join(f"`{item}`" for item in found_items)

    def _check_name_characters(self, name_to_check: str, allowed_set: set) -> tuple[bool, list[str]]:
        if not name_to_check:
            return True, []
        invalid_chars = []
        is_valid = True
        for char_val in name_to_check:
            if char_val not in allowed_set:
                is_valid = False
                if char_val not in invalid_chars:
                    invalid_chars.append(char_val)
        return is_valid, invalid_chars

    def _check_text_for_prohibited_words(self, text_to_check: str, prohibited_words_list: list[str]) -> tuple[bool, list[str]]:
        """Checks text for prohibited words (case-insensitive substring match)."""
        if not text_to_check or not prohibited_words_list:
            return False, []
        
        found_words = []
        text_to_check_lower = text_to_check.lower()
        for banned_word in prohibited_words_list: # Assumes banned_word in list is already lowercase
            if banned_word in text_to_check_lower:
                found_words.append(banned_word)
        
        return bool(found_words), list(set(found_words)) # Unique found words

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        alert_channel_id = await self.config.guild(guild).alert_channel()
        if not alert_channel_id: return
        alert_channel = guild.get_channel(alert_channel_id)
        if not alert_channel or not alert_channel.permissions_for(guild.me).send_messages: return

        alert_needed = False
        issues = []
        name_str = member.name
        nick_str = member.nick
        global_name_str = member.global_name
        
        prohibited_words = await self.config.guild(guild).prohibited_bio_words()

        # --- 1. Global Username (member.name) Checks ---
        username_is_char_compliant, username_bad_chars = self._check_name_characters(name_str, USERNAME_ALLOWED_CHAR_SET)
        username_has_prohibited_words, username_found_prohibited = self._check_text_for_prohibited_words(name_str, prohibited_words)

        if not username_is_char_compliant:
            alert_needed = True
            issues.append(f"**Global Username (`{name_str}`):** Contains restricted characters: {self._format_found_list(username_bad_chars)}")
        if username_has_prohibited_words:
            alert_needed = True
            issues.append(f"**Global Username (`{name_str}`):** Contains prohibited word(s): {self._format_found_list(username_found_prohibited)}")

        # --- 2. Server Nickname / Global Display Name Logic (Hierarchical) ---
        if nick_str:
            nick_is_char_compliant, nick_bad_chars = self._check_name_characters(nick_str, NICK_OR_GLOBAL_NAME_ALLOWED_CHAR_SET)
            nick_has_prohibited_words, nick_found_prohibited = self._check_text_for_prohibited_words(nick_str, prohibited_words)

            if not nick_is_char_compliant:
                alert_needed = True
                issues.append(f"**Server Nickname (`{nick_str}`):** Contains restricted characters: {self._format_found_list(nick_bad_chars)}")
            if nick_has_prohibited_words:
                alert_needed = True
                issues.append(f"**Server Nickname (`{nick_str}`):** Contains prohibited word(s): {self._format_found_list(nick_found_prohibited)}")
        else: # No Server Nickname
            if not global_name_str:
                alert_needed = True
                issues.append(f"**Profile Customization:** Neither server nickname nor global display name is set (displayed as global username: `{name_str}`).")
            else: # Global Display Name exists
                global_name_is_char_compliant, global_name_bad_chars = self._check_name_characters(global_name_str, NICK_OR_GLOBAL_NAME_ALLOWED_CHAR_SET)
                global_name_has_prohibited_words, global_name_found_prohibited = self._check_text_for_prohibited_words(global_name_str, prohibited_words)

                if not global_name_is_char_compliant:
                    alert_needed = True
                    issues.append(f"**Global Display Name (`{global_name_str}`):** Contains restricted characters: {self._format_found_list(global_name_bad_chars)}")
                if global_name_has_prohibited_words:
                    alert_needed = True
                    issues.append(f"**Global Display Name (`{global_name_str}`):** Contains prohibited word(s): {self._format_found_list(global_name_found_prohibited)}")
        
        if alert_needed:
            unique_issues = list(dict.fromkeys(issues))
            if not unique_issues: return

            embed = discord.Embed(
                title="⚠️ User Profile Policy Alert",
                description=f"User {member.mention} (`{member.id}`) has joined. Their profile may require attention regarding the following server rule(s):",
                color=discord.Color.orange(),
                timestamp=member.joined_at or discord.utils.utcnow()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="Issue(s) Detected:", value="\n".join(unique_issues), inline=False)
            
            try:
                await alert_channel.send(embed=embed)
            except discord.Forbidden:
                print(f"{self.qualified_name}: No permission to send message to channel {alert_channel_id} in guild {guild.id}.")
            except discord.HTTPException as e:
                print(f"{self.qualified_name}: Failed to send alert message in {guild.id}: {e}")

    # --- Settings for Name Checker part (ncset) ---
    @commands.group(name="namecheckerset", aliases=["ncset"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def namechecker_settings(self, ctx: commands.Context):
        """Manage name checking alert settings."""
        pass

    @namechecker_settings.command(name="channel")
    async def set_alert_channel_nc(self, ctx: commands.Context, channel: discord.TextChannel = None):
        guild = ctx.guild
        if channel:
            if not channel.permissions_for(guild.me).send_messages:
                await ctx.send(f"⚠️ I do not have permission to send messages in {channel.mention}. Please grant me 'Send Messages' permission there.")
                return
            await self.config.guild(guild).alert_channel.set(channel.id)
            await ctx.send(f"✅ Name policy alerts will now be sent to {channel.mention}.")
        else:
            await self.config.guild(guild).alert_channel.set(None)
            await ctx.send("✅ Name policy alerts have been disabled.")

    @namechecker_settings.command(name="show", aliases=["showsettings"])
    async def show_current_settings_nc(self, ctx: commands.Context):
        channel_id = await self.config.guild(ctx.guild).alert_channel()
        if channel_id:
            channel = ctx.guild.get_channel(channel_id)
            await ctx.send(f"Name policy alerts are currently sent to: {channel.mention}" if channel else "Alert channel for names configured but not found. Please set it again.")
        else:
            await ctx.send("Name policy alerts are currently disabled.")

    # --- Settings for Bio Checker part (bioset) ---
    @commands.group(name="bioset", aliases=["biocheckset"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def bioset(self, ctx: commands.Context):
        """Manage prohibited words/phrases for user bios ("About Me")."""
        pass

    @bioset.command(name="add")
    async def bioset_add(self, ctx: commands.Context, *, word_or_phrase: str):
        word_or_phrase_lower = word_or_phrase.lower() # Store lowercase for case-insensitive match
        async with self.config.guild(ctx.guild).prohibited_bio_words() as prohibited_list:
            if word_or_phrase_lower not in prohibited_list:
                prohibited_list.append(word_or_phrase_lower)
                await ctx.send(f"✅ Added '`{word_or_phrase}`' to the prohibited bio words list.")
            else:
                await ctx.send(f"ℹ️ '`{word_or_phrase}`' is already in the list.")

    @bioset.command(name="remove")
    async def bioset_remove(self, ctx: commands.Context, *, word_or_phrase: str):
        word_or_phrase_lower = word_or_phrase.lower()
        async with self.config.guild(ctx.guild).prohibited_bio_words() as prohibited_list:
            if word_or_phrase_lower in prohibited_list:
                prohibited_list.remove(word_or_phrase_lower)
                await ctx.send(f"✅ Removed '`{word_or_phrase}`' from the prohibited bio words list.")
            else:
                await ctx.send(f"ℹ️ '`{word_or_phrase}`' was not found in the list.")

    @bioset.command(name="list")
    async def bioset_list(self, ctx: commands.Context):
        prohibited_list = await self.config.guild(ctx.guild).prohibited_bio_words()
        if not prohibited_list:
            await ctx.send("ℹ️ There are currently no prohibited words/phrases set for bios.")
            return
        
        formatted_list = "\n".join(f"- `{item}`" for item in prohibited_list)
        embed = discord.Embed(title="Prohibited Bio Words/Phrases", description=formatted_list, color=await ctx.embed_color())
        await ctx.send(embed=embed)

    @bioset.command(name="clear")
    async def bioset_clear(self, ctx: commands.Context):
        async with self.config.guild(ctx.guild).prohibited_bio_words() as prohibited_list:
            if not prohibited_list:
                await ctx.send("ℹ️ The prohibited bio words list is already empty.")
                return
            prohibited_list.clear()
        await ctx.send("✅ All prohibited words/phrases for bios have been cleared.")

    # --- Comprehensive Profile Check Command ---
    @commands.command(name="checkprofile", aliases=["inspectprofile"])
    @commands.guild_only() 
    @commands.bot_has_permissions(embed_links=True)
    @commands.is_owner() # Or your preferred permission check
    async def check_profile_command(self, ctx: commands.Context, member_to_check: discord.Member):
        """
        Checks a user's full profile against server rules and states if they would be flagged.
        Gracefully handles bio fetch failures.
        """
        name_str = member_to_check.name
        nick_str = member_to_check.nick
        global_name_str = member_to_check.global_name
        effective_display_name = member_to_check.display_name

        prohibited_words = await self.config.guild(ctx.guild).prohibited_bio_words()

        response_lines = [
            f"**Profile Check for User:** {member_to_check.mention} (ID: `{member_to_check.id}`)",
            f"  **Effective Display Name on this Server:** `{effective_display_name}`",
            f"  **1. Global Username (account):** `{name_str}`",
            f"  **2. Server Nickname (this server):** `{nick_str if nick_str else 'Not set'}`",
            f"  **3. Global Display Name (profile):** `{global_name_str if global_name_str else 'Not set'}`",
        ]
        
        # --- Bio Fetching and Status ---
        profile_obj = None
        bio_content_str = None
        bio_fetch_status_message = ""

        if not hasattr(member_to_check, 'fetch_profile'):
            bio_fetch_status_message = "⚠️ **Bio Check Skipped:** `Workspace_profile` method is missing from the Member object. This indicates a potential discord.py installation or environment issue."
            # Log this critical issue to console for the bot owner
            print(f"[CRITICAL ERROR in checkprofile for {ctx.guild.id}] User {member_to_check.id}: member_to_check (type: {type(member_to_check)}) is missing 'fetch_profile'. isinstance(discord.User): {isinstance(member_to_check, discord.User)}")
        else:
            try:
                profile_obj = await member_to_check.fetch_profile()
                if profile_obj and profile_obj.bio:
                    bio_content_str = profile_obj.bio
                    bio_fetch_status_message = f"✅ Bio fetched ({len(bio_content_str)} characters)."
                elif profile_obj: # Profile fetched but no bio content
                    bio_fetch_status_message = "ℹ️ Bio is set, but empty."
                else: # profile_obj itself is None (API returned nothing)
                    bio_fetch_status_message = "⚠️ Profile data could not be returned by the API."
            except discord.HTTPException as e:
                bio_fetch_status_message = f"⚠️ Could not fetch bio due to API error (Status: {e.status})."
                print(f"[NameChecker-checkprofile] HTTPException during fetch_profile: {e}")
            except Exception as e: # Catch any other unexpected errors
                bio_fetch_status_message = f"⚠️ An unexpected error occurred while fetching bio: {type(e).__name__}."
                print(f"[NameChecker-checkprofile] Unexpected error during fetch_profile: {e}")
        
        response_lines.append(f"  **4. Bio ('About Me') Status:** {bio_fetch_status_message}")
        response_lines.append("-" * 30)
        response_lines.append("**Rule Evaluation & Flagging Status:**")

        alert_would_be_needed = False
        issues_detected = []

        # --- Username Checks ---
        username_is_char_compliant, username_bad_chars = self._check_name_characters(name_str, USERNAME_ALLOWED_CHAR_SET)
        username_has_prohibited_words, username_found_prohibited = self._check_text_for_prohibited_words(name_str, prohibited_words)
        response_lines.append(f"  - Global Username (`{name_str}`):")
        response_lines.append(f"    - Char Compliance: {'✅ Compliant' if username_is_char_compliant else f'❌ NON-COMPLIANT (Chars: {self._format_found_list(username_bad_chars)})'}")
        response_lines.append(f"    - Prohibited Words: {'✅ None found' if not username_has_prohibited_words else f'❌ FOUND (Words: {self._format_found_list(username_found_prohibited)})'}")
        if not username_is_char_compliant:
            alert_would_be_needed = True
            issues_detected.append(f"Global Username (`{name_str}`): Contains restricted characters: {self._format_found_list(username_bad_chars)}")
        if username_has_prohibited_words:
            alert_would_be_needed = True
            issues_detected.append(f"Global Username (`{name_str}`): Contains prohibited word(s): {self._format_found_list(username_found_prohibited)}")

        # --- Server Nickname / Global Display Name Logic ---
        if nick_str:
            response_lines.append(f"  - Server Nickname (`{nick_str}`): IS SET.")
            nick_is_char_compliant, nick_bad_chars = self._check_name_characters(nick_str, NICK_OR_GLOBAL_NAME_ALLOWED_CHAR_SET)
            nick_has_prohibited_words, nick_found_prohibited = self._check_text_for_prohibited_words(nick_str, prohibited_words)
            response_lines.append(f"    - Char Compliance: {'✅ Compliant' if nick_is_char_compliant else f'❌ NON-COMPLIANT (Chars: {self._format_found_list(nick_bad_chars)})'}")
            response_lines.append(f"    - Prohibited Words: {'✅ None found' if not nick_has_prohibited_words else f'❌ FOUND (Words: {self._format_found_list(nick_found_prohibited)})'}")
            if not nick_is_char_compliant:
                alert_would_be_needed = True
                issues_detected.append(f"Server Nickname (`{nick_str}`): Contains restricted characters: {self._format_found_list(nick_bad_chars)}")
            if nick_has_prohibited_words:
                alert_would_be_needed = True
                issues_detected.append(f"Server Nickname (`{nick_str}`): Contains prohibited word(s): {self._format_found_list(nick_found_prohibited)}")
        else: # No Server Nickname
            response_lines.append(f"  - Server Nickname: ⚠️ NOT SET.")
            if not global_name_str:
                response_lines.append(f"  - Global Display Name: ⚠️ NOT SET.")
                alert_would_be_needed = True
                issues_detected.append(f"Profile Customization: Neither server nickname nor global display name is set (displayed as: `{name_str}`).")
            else: # Global Display Name exists
                response_lines.append(f"  - Global Display Name (`{global_name_str}`): IS SET (acting as primary custom display).")
                global_name_is_char_compliant, global_name_bad_chars = self._check_name_characters(global_name_str, NICK_OR_GLOBAL_NAME_ALLOWED_CHAR_SET)
                global_name_has_prohibited_words, global_name_found_prohibited = self._check_text_for_prohibited_words(global_name_str, prohibited_words)
                response_lines.append(f"    - Char Compliance: {'✅ Compliant' if global_name_is_char_compliant else f'❌ NON-COMPLIANT (Chars: {self._format_found_list(global_name_bad_chars)})'}")
                response_lines.append(f"    - Prohibited Words: {'✅ None found' if not global_name_has_prohibited_words else f'❌ FOUND (Words: {self._format_found_list(global_name_found_prohibited)})'}")
                if not global_name_is_char_compliant:
                    alert_would_be_needed = True
                    issues_detected.append(f"Global Display Name (`{global_name_str}`): Contains restricted characters: {self._format_found_list(global_name_bad_chars)}")
                if global_name_has_prohibited_words:
                    alert_would_be_needed = True
                    issues_detected.append(f"Global Display Name (`{global_name_str}`): Contains prohibited word(s): {self._format_found_list(global_name_found_prohibited)}")
        
        # --- Bio Prohibited Word Check ---
        if bio_content_str: # Only check if bio_content_str was successfully populated
            bio_has_prohibited_words, bio_found_prohibited = self._check_text_for_prohibited_words(bio_content_str, prohibited_words)
            response_lines.append(f"  - Bio ('About Me') Prohibited Words Check: {'✅ None found' if not bio_has_prohibited_words else f'❌ FOUND (Words: {self._format_found_list(bio_found_prohibited)})'}")
            if bio_has_prohibited_words:
                alert_would_be_needed = True
                issues_detected.append(f"Bio ('About Me'): Contains prohibited word(s): {self._format_found_list(bio_found_prohibited)}")
                response_lines.append(f"    - Bio Preview (first 100 chars): `{discord.utils.escape_markdown(bio_content_str[:100])}{'...' if len(bio_content_str)>100 else ''}`")
        elif bio_fetch_status_message.startswith("⚠️"): # If there was an error or issue fetching bio
            response_lines.append(f"  - Bio ('About Me') Prohibited Words Check: Not performed due to bio access issue.")
        else: # Bio is empty or not set, but no error fetching.
            response_lines.append(f"  - Bio ('About Me') Prohibited Words Check: ✅ Not set, so no prohibited words.")


        response_lines.append("-" * 30)
        if alert_would_be_needed:
            response_lines.append("🚨 **Flagging Conclusion:** This user's profile WOULD BE FLAGGED.")
            unique_issues = list(dict.fromkeys(issues_detected)) # Basic deduplication
            if unique_issues:
                 response_lines.append("**Reason(s):**")
                 for issue in unique_issues: response_lines.append(f"  - {issue}")
        else:
            response_lines.append("✅ **Flagging Conclusion:** This user's profile WOULD NOT BE FLAGGED.")
        
        output_message = "\n".join(response_lines)
        if len(output_message) > 1990: # Discord message length limit
            parts = [output_message[i:i + 1990] for i in range(0, len(output_message), 1990)]
            for part in parts:
                await ctx.send(part)
        else:
            await ctx.send(output_message)