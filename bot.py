import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Force reload environment variables from .env
load_dotenv(override=True)

TOKEN = os.getenv("DISCORD_TOKEN")
STATS_CHANNEL_ID = int(os.getenv("STATS_CHANNEL_ID", "0").strip())

raw_msg_id = os.getenv("STATS_MESSAGE_ID", "").strip().strip("'\"")
STATS_MESSAGE_ID = int(raw_msg_id) if raw_msg_id.isdigit() else None

intents = discord.Intents.default()
intents.guilds = True
intents.members = True  # Required in Discord Developer Portal

bot = commands.Bot(command_prefix="!", intents=intents)

# Server role categories matching your onboarding roles
ROLE_CATEGORIES = {
    "Ruleset": ["PVP", "PVE", "RP", "HC"],
    "Faction": ["ALLIANCE", "HORDE"],
    "Classes": ["MAGE", "ROGUE", "WARRIOR", "DRUID", "WARLOCK", "PALADIN", "HUNTER", "PRIEST", "SHAMAN"],
    "Roles": ["DPS", "TANK", "HEAL"]
}

# Mapping of uppercase role names to custom server emoji names
EMOJI_NAME_MAP = {
    "TANK": "tank",
    "HEAL": "heal",
    "DPS": "dps",
    "WARRIOR": "warrior",
    "WARLOCK": "warlock",
    "SHAMAN": "shaman",
    "ROGUE": "rogue",
    "PRIEST": "priest",
    "PALADIN": "paladin",
    "MAGE": "mage",
    "HUNTER": "hunter",
    "DRUID": "druid",
    "HORDE": "horde",
    "ALLIANCE": "alliance",
    "PVP": "pvp",
    "PVE": "pve",
    "RP": "rp",
    "HC": "hc"
}

def find_role_case_insensitive(guild: discord.Guild, name: str):
    """Finds a role regardless of capitalization."""
    for role in guild.roles:
        if role.name.lower() == name.lower():
            return role
    return None

def find_emoji(guild: discord.Guild, role_name: str) -> str:
    """Finds custom server emoji by name, or returns empty string if not found."""
    target_emoji_name = EMOJI_NAME_MAP.get(role_name.upper(), role_name.lower())
    emoji = discord.utils.get(guild.emojis, name=target_emoji_name)
    if emoji:
        return str(emoji)
    return ""

class RoleSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        options = []
        added_role_ids = set()
        
        for category, role_names in ROLE_CATEGORIES.items():
            for name in role_names:
                role = find_role_case_insensitive(guild, name)
                if role and role.id not in added_role_ids:
                    added_role_ids.add(role.id)
                    count = len(role.members)
                    
                    target_emoji_name = EMOJI_NAME_MAP.get(role.name.upper(), role.name.lower())
                    emoji_obj = discord.utils.get(guild.emojis, name=target_emoji_name)

                    options.append(
                        discord.SelectOption(
                            label=f"{role.name} ({count})",
                            description=f"View members with the {role.name} role",
                            value=str(role.id),
                            emoji=emoji_obj if emoji_obj else None
                        )
                    )

        super().__init__(
            placeholder="Select a role to see who holds it...",
            min_values=1,
            max_values=1,
            options=options[:25]  # Discord maximum select menu options limit
        )

    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        role = interaction.guild.get_role(role_id)

        if not role:
            await interaction.response.send_message("Role not found.", ephemeral=True)
            return

        members = [m.display_name for m in role.members]
        if not members:
            content = f"**{role.name}** currently has `0` members."
        else:
            displayed_members = members[:40]
            member_list = "\n".join(f"• {name}" for name in displayed_members)
            if len(members) > 40:
                member_list += f"\n\n*...and {len(members) - 40} more.*"

            content = f"### Members with {role.name} ({len(members)}):\n{member_list}"

        # Ephemeral popup visible only to the user who made the selection
        await interaction.response.send_message(content, ephemeral=True)

class RoleSelectView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=None)  # Persistent view across restarts
        self.add_item(RoleSelect(guild))

async def refresh_stats_dashboard(guild: discord.Guild):
    global STATS_MESSAGE_ID

    if not STATS_CHANNEL_ID:
        print("[ERROR] STATS_CHANNEL_ID is not set in .env file.")
        return

    channel = guild.get_channel(STATS_CHANNEL_ID)
    if not channel:
        print(f"[ERROR] Could not find channel with ID {STATS_CHANNEL_ID}")
        return

    embed = discord.Embed(
        title="🛡️ ASGARD • Server Role Statistics",
        description="Real-time counts for all server roles. Use the menu below to view specific members.",
        color=0x2b2d31
    )

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    for category_name, role_names in ROLE_CATEGORIES.items():
        formatted_list = []
        checked_roles = set()
        
        for name in role_names:
            role = find_role_case_insensitive(guild, name)
            if role and role.id not in checked_roles:
                checked_roles.add(role.id)
                emoji_str = find_emoji(guild, role.name)
                prefix = f"{emoji_str} " if emoji_str else "• "
                formatted_list.append(f"{prefix}**{role.name}**: `{len(role.members)}`")

        if formatted_list:
            icons = {"Ruleset": "📜", "Faction": "⚔️", "Classes": "🧙‍♂️", "Roles": "🛡️"}
            icon = icons.get(category_name, "📊")
            
            embed.add_field(
                name=f"{icon} {category_name}",
                value="\n".join(formatted_list),
                inline=True
            )

    embed.set_footer(text="🔄 Auto-updates in real-time | Asgard WoW Community")
    view = RoleSelectView(guild)

    # 1. Edit existing message ID if configured
    if STATS_MESSAGE_ID:
        try:
            message = await channel.fetch_message(STATS_MESSAGE_ID)
            await message.edit(embed=embed, view=view)
            return
        except discord.NotFound:
            pass
        except Exception as e:
            print(f"[WARNING] Could not edit existing message: {e}")

    # 2. Check for existing bot message in recent channel history
    async for msg in channel.history(limit=10):
        if msg.author == bot.user and msg.embeds:
            STATS_MESSAGE_ID = msg.id
            await msg.edit(embed=embed, view=view)
            return

    # 3. Create fresh message if channel is clear
    message = await channel.send(embed=embed, view=view)
    STATS_MESSAGE_ID = message.id
    print(f"\n==================================================")
    print(f"[SUCCESS] New message created! Add this to your .env:")
    print(f"STATS_MESSAGE_ID={message.id}")
    print(f"==================================================\n")

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user.name}")
    for guild in bot.guilds:
        await refresh_stats_dashboard(guild)

@bot.event
async def on_member_update(before, after):
    if before.roles != after.roles:
        await refresh_stats_dashboard(after.guild)

@bot.event
async def on_member_join(member):
    await refresh_stats_dashboard(member.guild)

@bot.event
async def on_member_remove(member):
    await refresh_stats_dashboard(member.guild)

if __name__ == "__main__":
    if not TOKEN:
        print("[ERROR] DISCORD_TOKEN is missing in .env file.")
    else:
        bot.run(TOKEN)