from .namechecker import NameChecker

async def setup(bot):
    cog_instance = NameChecker(bot)
    await bot.add_cog(cog_instance)