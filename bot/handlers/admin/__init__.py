"""
Обработчики админ-панели.
"""

from .users_handler import handle_admin_users
from .moderation_handler import handle_admin_moderation, handle_moderation_delete, handle_moderation_restore, handle_moderation_change_type
from .notifications_handler import handle_admin_notifications, handle_notification_callbacks
from .promo_handler import handle_admin_promo_links, handle_promo_create, handle_promo_stats, handle_promo_delete
from .referral_stats_handler import handle_admin_referral_stats
from .daily_stats_handler import handle_admin_daily_stats
from .archive_handler import handle_admin_archive
from .test_handler import handle_admin_test, handle_admin_test_subscription

__all__ = [
    'handle_admin_users',
    'handle_admin_moderation',
    'handle_moderation_delete',
    'handle_moderation_restore',
    'handle_moderation_change_type',
    'handle_admin_notifications',
    'handle_notification_callbacks',
    'handle_admin_promo_links',
    'handle_promo_create',
    'handle_promo_stats',
    'handle_promo_delete',
    'handle_admin_referral_stats',
    'handle_admin_daily_stats',
    'handle_admin_archive',
    'handle_admin_test',
    'handle_admin_test_subscription',
]
