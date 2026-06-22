# Config package

from config.settings import Settings, settings

__all__ = ['settings', 'Settings']

# Merge helper: also expose get_settings if present in migrated files
try:
	from config.settings import get_settings
	__all__.append('get_settings')
except Exception:
	pass