"""App version and change history.

When releasing a new version: bump VERSION and add an entry at the TOP of CHANGELOG.
Every entry is bilingual: "title" and "changes" hold both "en" and "fa".
Numbering: MAJOR.MINOR.PATCH
  - PATCH (1.2.0 -> 1.2.1): small fixes
  - MINOR (1.2.0 -> 1.3.0): new features
  - MAJOR (1.x -> 2.0.0): big redesigns or changes that need extra setup
"""

VERSION = "1.4.0"

CHANGELOG = [
    {
        "version": "1.4.0",
        "date": "2026-10-06",
        "title": {
            "en": "English and Persian interface",
            "fa": "رابط دوزبانه: انگلیسی و فارسی",
        },
        "changes": {
            "en": [
                "The whole interface now exists in English and Persian. Switch language from the header; your choice is remembered.",
                "English is now the default language (set DEFAULT_LANGUAGE=fa in .env to keep Persian as the default).",
                "New Settings page for the app language and your time zone (no longer fixed to Europe/Berlin).",
                "Event warnings (unclear date format, missing year, guessed time zone, ...) are now translated automatically instead of being stored in one language.",
                "The page direction (left-to-right or right-to-left) follows the language; times, dates, emails and links always stay left-to-right.",
            ],
            "fa": [
                "کل رابط کاربری حالا انگلیسی و فارسی دارد. زبان را از بالای صفحه عوض کن؛ انتخابت یادآوری می‌شود.",
                "زبان پیش‌فرض حالا انگلیسی است (برای فارسی به‌عنوان پیش‌فرض، DEFAULT_LANGUAGE=fa را در .env بگذار).",
                "صفحه‌ی تنظیمات برای زبان برنامه و منطقه‌ی زمانی اضافه شد (دیگر ثابت روی Europe/Berlin نیست).",
                "هشدارهای قرارها (قالب نامشخص تاریخ، نبودن سال، منطقه‌ی زمانی حدسی و ...) حالا خودکار ترجمه می‌شوند.",
                "جهت صفحه با زبان عوض می‌شود؛ ساعت‌ها، تاریخ‌ها، ایمیل‌ها و لینک‌ها همیشه چپ‌به‌راست می‌مانند.",
            ],
        },
    },
    {
        "version": "1.3.1",
        "date": "2026-10-04",
        "title": {"en": "Time display fix", "fa": "اصلاح نمایش ساعت"},
        "changes": {
            "en": [
                "Times on event cards are no longer shown reversed (for example 30:10 instead of 10:30).",
                "The \"please check\" note appears only for an unclear date, time or time zone, and is written in Persian.",
            ],
            "fa": [
                "ساعت‌ها در کارت قرار دیگر برعکس نمایش داده نمی‌شوند (مثلاً ۳۰:۱۰ به‌جای ۱۰:۳۰).",
                "یادداشت «لطفاً چک کن» فقط برای ابهام در تاریخ، ساعت یا منطقه‌ی زمانی و به فارسی نوشته می‌شود.",
            ],
        },
    },
    {
        "version": "1.3.0",
        "date": "2026-10-04",
        "title": {"en": "Version number and changelog", "fa": "شماره‌ی نسخه و تاریخچه‌ی تغییرات"},
        "changes": {
            "en": [
                "The version number is shown at the bottom of every page.",
                "A Changelog page was added to see the features of each version.",
            ],
            "fa": [
                "شماره‌ی نسخه پایین همه‌ی صفحه‌ها نمایش داده می‌شود.",
                "صفحه‌ی «تاریخچه‌ی تغییرات» برای دیدن قابلیت‌های هر نسخه اضافه شد.",
            ],
        },
    },
    {
        "version": "1.2.0",
        "date": "2026-10-04",
        "title": {"en": "Google Calendar connection", "fa": "اتصال به تقویم گوگل"},
        "changes": {
            "en": [
                "The next 7 days of your calendar are shown at the top of the dashboard.",
                "Meetings in received emails and in your sent replies are found automatically, with an \"Add to calendar\" button.",
                "The time zone of a meeting is detected from its place, with a warning when it differs from your local time.",
                "A conflict warning appears when a meeting overlaps another event in your calendar.",
                "You can send a calendar invitation to the other person.",
                "An \"Event\" tag appears next to emails that contain meetings.",
                "Dates are shown in your local time, not server time.",
            ],
            "fa": [
                "نمایش برنامه‌های ۷ روز آینده‌ی تقویم بالای داشبورد.",
                "پیدا کردن خودکار قرارها در ایمیل‌های دریافتی و جواب‌های ارسالی، با دکمه‌ی «افزودن به تقویم».",
                "تشخیص منطقه‌ی زمانی قرار از روی مکان و هشدار وقتی با وقت محلی فرق دارد.",
                "هشدار تداخل وقتی زمان قرار با برنامه‌ی دیگری در تقویم هم‌زمان است.",
                "امکان فرستادن دعوت‌نامه‌ی تقویم برای طرف مقابل.",
                "برچسب «قرار» کنار ایمیل‌هایی که قرار دارند.",
                "تاریخ‌ها به وقت محلی تو نمایش داده می‌شوند، نه وقت سرور.",
            ],
        },
    },
    {
        "version": "1.1.0",
        "date": "2026-10-03",
        "title": {"en": "Changing the Gmail account", "fa": "تغییر حساب جیمیل"},
        "changes": {
            "en": ["A \"Change account\" button to switch between the test mailbox and the main mailbox."],
            "fa": ["دکمه‌ی «تغییر حساب» برای جابه‌جا شدن بین ایمیل آزمایشی و ایمیل اصلی."],
        },
    },
    {
        "version": "1.0.0",
        "date": "2026-10-03",
        "title": {"en": "First version", "fa": "نسخه‌ی اول"},
        "changes": {
            "en": [
                "New Gmail messages are read automatically; newsletters and automated mail are skipped.",
                "Reply drafts are written with Claude, in the sender's own language.",
                "A task queue to review, edit, rewrite, reject, or approve and send each reply.",
                "Replies are sent in the same email thread, never automatically.",
            ],
            "fa": [
                "خواندن خودکار ایمیل‌های جدید جیمیل و کنار گذاشتن خبرنامه‌ها و ایمیل‌های خودکار.",
                "نوشتن پیش‌نویس جواب با Claude، به زبان خود فرستنده.",
                "صف تسک‌ها برای بررسی، ویرایش، بازنویسی، رد یا تأیید و ارسال هر جواب.",
                "ارسال جواب در همان رشته‌ی ایمیل، بدون ارسال خودکار.",
            ],
        },
    },
]
