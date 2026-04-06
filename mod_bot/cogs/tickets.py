import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime, timezone
from typing import Optional

from config.settings import Config


class TicketDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="🐛 Bug Report", description="Report a bug or glitch", emoji="🐛"),
            discord.SelectOption(label="💰 Economy Issue", description="Lost SC, transaction issues", emoji="💰"),
            discord.SelectOption(label="⚖️ Ban Appeal", description="Appeal a ban", emoji="⚖️"),
            discord.SelectOption(label="🎖️ Beta Tester", description="Apply for beta tester role", emoji="🎖️"),
            discord.SelectOption(label="❓ General Support", description="Other questions", emoji="❓"),
        ]
        super().__init__(placeholder="Select ticket type...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        category_name = "SUPPORT"
        category = discord.utils.get(interaction.guild.categories, name=category_name)

        if not category:
            category = await interaction.guild.create_category(category_name)

        ticket_type = self.values[0]
        channel_name = f"ticket-{interaction.user.name}-{interaction.user.discriminator}"

        mod_role = interaction.guild.get_role(Config.MOD_ROLE_ID) if Config.MOD_ROLE_ID else None

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }

        if mod_role:
            overwrites[mod_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        channel = await interaction.guild.create_text_channel(
            channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"Ticket type: {ticket_type} | Created by: {interaction.user.id}"
        )

        async with interaction.client.db.acquire() as conn:
            await conn.execute("""
                INSERT INTO tickets (discord_id, category, channel_id, opened_at)
                VALUES ($1, $2, $3, NOW())
            """, interaction.user.id, ticket_type, channel.id)

        embed = discord.Embed(
            title=f"🎫 {ticket_type}",
            description=f"Support ticket created by {interaction.user.mention}",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )

        player = await interaction.client.services.player.get(interaction.user.id)

        if player:
            embed.add_field(
                name="Player Snapshot",
                value=f"**Wallet:** {player.get('wallet', 0)} SC\n**Bank:** {player.get('bank', 0)} SC\n**Reputation:** {player.get('reputation', 0)}\n**Jailed:** {'Yes' if player.get('is_jailed') else 'No'}",
                inline=False
            )

        embed.set_footer(text="A moderator will assist you shortly. Use /close to close this ticket.")

        view = discord.ui.View()
        close_button = discord.ui.Button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
        view.add_item(close_button)

        await channel.send(embed=embed, view=view)

        await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)

        if mod_role:
            await channel.send(f"{mod_role.mention} New ticket created.")


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown())


class TicketCloseButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        async with interaction.client.db.acquire() as conn:
            ticket = await conn.fetchrow("""
                SELECT * FROM tickets WHERE channel_id = $1 AND status = 'open'
            """, interaction.channel.id)

        if not ticket:
            await interaction.followup.send("❌ This ticket is already closed.", ephemeral=True)
            return

        async with interaction.client.db.acquire() as conn:
            await conn.execute("""
                UPDATE tickets SET status = 'closed', closed_at = NOW(), closed_by = $2
                WHERE channel_id = $1
            """, interaction.channel.id, interaction.user.id)

        category = discord.utils.get(interaction.guild.categories, name="CLOSED TICKETS")
        if not category:
            category = await interaction.guild.create_category("CLOSED TICKETS")

        await interaction.channel.edit(
            category=category,
            name=f"closed-{interaction.channel.name}",
            slowmode_delay=0
        )

        embed = discord.Embed(
            title="🔒 Ticket Closed",
            description=f"Closed by {interaction.user.mention}\nThis channel will be archived.",
            color=discord.Color.gray(),
            timestamp=datetime.now(timezone.utc)
        )

        await interaction.channel.send(embed=embed)

        user = interaction.guild.get_member(ticket["discord_id"])
        if user:
            try:
                dm_embed = discord.Embed(
                    title="🎫 Ticket Closed",
                    description=f"Your ticket ({ticket['category']}) has been closed by a moderator.",
                    color=discord.Color.blue()
                )
                await user.send(embed=dm_embed)
            except Exception:
                pass

        await interaction.followup.send("✅ Ticket closed.", ephemeral=True)


class TicketsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("simcoin.mod.tickets")

    @app_commands.command(name="ticket_panel", description="[MOD] Create ticket creation panel")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="Channel to put the ticket panel in")
    async def ticket_panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        embed = discord.Embed(
            title="🎫 Support Tickets",
            description="Select a ticket type from the dropdown below to create a support ticket.",
            color=discord.Color.blue()
        )

        view = TicketView()

        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Ticket panel created in {channel.mention}", ephemeral=True)

    @app_commands.command(name="close", description="Close current ticket")
    async def close(self, interaction: discord.Interaction):
        async with self.bot.db.acquire() as conn:
            ticket = await conn.fetchrow("""
                SELECT * FROM tickets WHERE channel_id = $1 AND status = 'open'
            """, interaction.channel.id)

        if not ticket:
            await interaction.response.send_message("❌ This is not a ticket channel.", ephemeral=True)
            return

        view = discord.ui.View()
        view.add_item(TicketCloseButton())

        await interaction.response.send_message("⚠️ Are you sure you want to close this ticket?", view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(TicketsCog(bot))