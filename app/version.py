"""App version and change history.

When releasing a new version: bump VERSION and add an entry at the TOP of CHANGELOG.
Every entry is bilingual: "title" and "changes" hold both "en" and "fa".
Numbering: MAJOR.MINOR.PATCH
  - PATCH (1.2.0 -> 1.2.1): small fixes
  - MINOR (1.2.0 -> 1.3.0): new features
  - MAJOR (1.x -> 2.0.0): big redesigns or changes that need extra setup
"""

VERSION = "1.9.1"

CHANGELOG = [
    {
        "version": "1.9.1",
        "date": "2026-10-10",
        "title": {
            "en": "Fresh look and dark mode",
            "fa": "ظاهر تازه و حالت تاریک",
        },
        "changes": {
            "en": [
                "Warmer, calmer colors, softer cards and a tidier header on every page.",
                "Dark mode: the dashboard follows your phone or computer setting.",
                "The language switch is now a small toggle; the selected tab and the open email stand out more.",
            ],
            "fa": [
                "رنگ‌های گرم‌تر و آرام‌تر، کارت‌های نرم‌تر و هدر مرتب‌تر در همه‌ی صفحه‌ها.",
                "حالت تاریک: داشبورد از تنظیم گوشی یا کامپیوترت پیروی می‌کند.",
                "انتخاب زبان حالا یک کلید کوچک است و تب انتخاب‌شده و ایمیل باز بهتر دیده می‌شوند.",
            ],
        },
    },
    {
        "version": "1.9.0",
        "date": "2026-10-10",
        "title": {
            "en": "Review page for the film dashboard",
            "fa": "صفحه‌ی بررسی داشبورد فیلم",
        },
        "changes": {
            "en": [
                "New \"Film dashboard\" page: the funds and events the pipeline found, each with its dates and the exact quotes they came from.",
                "Approve or reject each record, with an optional note. Approving does not publish anything yet; the website sync comes later.",
                "The page appears only when FILMDASH_DATABASE_URL is set in .env (see pipeline/README.md).",
            ],
            "fa": [
                "صفحه‌ی تازه‌ی «داشبورد فیلم»: فاندها و رویدادهایی که پایپ‌لاین پیدا کرده، هر کدام با تاریخ‌ها و نقل‌قول دقیقی که از آن آمده‌اند.",
                "هر رکورد را می‌شود با یک یادداشت اختیاری تأیید یا رد کرد. تأیید هنوز چیزی را در سایت منتشر نمی‌کند؛ همگام‌سازی با سایت بعداً می‌آید.",
                "این صفحه فقط وقتی دیده می‌شود که FILMDASH_DATABASE_URL در .env تنظیم شده باشد (راهنما در pipeline/README.md).",
            ],
        },
    },
    {
        "version": "1.8.1",
        "date": "2026-10-07",
        "title": {
            "en": "Delete straight from the list",
            "fa": "حذف مستقیم از فهرست",
        },
        "changes": {
            "en": [
                "Every email row now shows a small trash icon next to the arrow, so you can delete without opening the row. It still asks you to confirm first.",
            ],
            "fa": [
                "کنار فلش هر ردیف ایمیل حالا یک آیکون سطل زباله هست، تا بدون باز کردن ردیف بتوانی حذفش کنی. باز هم اول تأیید می‌گیرد.",
            ],
        },
    },
    {
        "version": "1.8.0",
        "date": "2026-10-07",
        "title": {
            "en": "Delete emails from the dashboard",
            "fa": "حذف ایمیل‌ها از داشبورد",
        },
        "changes": {
            "en": [
                "Every open row now has a Delete button. It asks you to confirm first, because a deleted email cannot be brought back.",
                "Deleting removes the email, its draft and its suggested events from every tab. Gmail is not touched, and the same email is never read again.",
            ],
            "fa": [
                "هر ردیف باز حالا یک دکمه‌ی «حذف» دارد. اول از تو تأیید می‌گیرد، چون ایمیل حذف‌شده برنمی‌گردد.",
                "حذف، ایمیل و پیش‌نویس و قرارهای پیشنهادی‌اش را از همه‌ی تب‌ها برمی‌دارد. جیمیل دست نمی‌خورد و همان ایمیل دوباره خوانده نمی‌شود.",
            ],
        },
    },
    {
        "version": "1.7.0",
        "date": "2026-10-07",
        "title": {
            "en": "Open emails inline, right in the list",
            "fa": "باز کردن ایمیل‌ها همان‌جا، داخل فهرست",
        },
        "changes": {
            "en": [
                "Every row in every tab is now an accordion: click it to open the details right below it, click again to close. Only one row is open at a time.",
                "Everything you could do on the email page you can now do inside the open row: read the original email, edit, rewrite, save, approve and send or reject the draft, add or dismiss events, mark mail as done, draft a reply anyway, and put a rejected email back.",
                "Actions no longer reload the page. The row updates in place, a small message tells you what happened, and the tab counts change. A row that no longer belongs to its tab (for example after sending) disappears from it.",
                "The details are loaded only when you open a row, so the dashboard opens faster. Text you typed into a draft stays when you close and re-open a row.",
                "The Events tab rows are accordions too, with the editable event card inside.",
                "Links like /#task-123 open that row. Without JavaScript the page still works: a row opens with a normal click and every action returns you to the dashboard with that row open. The old email page /tasks/123 still works as a fallback.",
                "A narrower, single-column layout that fits phones (no sideways scrolling, bigger tap targets) and follows the language direction. English is the default language and the EN | FA choice is remembered.",
            ],
            "fa": [
                "هر ردیف در هر تب حالا آکاردئون است: روی آن کلیک کن تا جزئیاتش درست زیر خودش باز شود و دوباره کلیک کن تا بسته شود. فقط یک ردیف در یک زمان باز است.",
                "هر کاری که در صفحه‌ی جدای ایمیل می‌شد کرد، حالا داخل ردیف باز هم شدنی است: خواندن ایمیل اصلی، ویرایش، بازنویسی، ذخیره، تأیید و ارسال یا رد پیش‌نویس، افزودن یا ردِ قرار، «انجام شد» برای ایمیل‌های بدون جواب، نوشتن جواب به‌هرحال، و برگرداندن ایمیل ردشده.",
                "کارها دیگر صفحه را دوباره بارگذاری نمی‌کنند. ردیف همان‌جا به‌روز می‌شود، یک پیام کوتاه می‌گوید چه شد و شمارنده‌ی تب‌ها عوض می‌شود. ردیفی که دیگر به آن تب تعلق ندارد (مثلاً بعد از ارسال) از آن ناپدید می‌شود.",
                "جزئیات فقط وقتی ردیف را باز می‌کنی بارگذاری می‌شود، پس داشبورد سریع‌تر باز می‌شود. متنی که در پیش‌نویس تایپ کرده‌ای با بستن و دوباره باز کردن ردیف از بین نمی‌رود.",
                "ردیف‌های تب رویدادها هم آکاردئون‌اند و کارت قابل‌ویرایش رویداد داخلشان است.",
                "لینک‌هایی مثل ‎/#task-123‎ همان ردیف را باز می‌کنند. بدون جاوااسکریپت هم صفحه کار می‌کند: ردیف با کلیک معمولی باز می‌شود و هر کار تو را به داشبورد با همان ردیف باز برمی‌گرداند. صفحه‌ی قدیمی ‎/tasks/123‎ هم به‌عنوان جایگزین کار می‌کند.",
                "چیدمان تک‌ستونی و باریک‌تر که روی گوشی جا می‌شود (بدون اسکرول افقی و با دکمه‌های بزرگ‌تر) و با جهت زبان عوض می‌شود. زبان پیش‌فرض انگلیسی است و انتخاب EN | FA به خاطر سپرده می‌شود.",
            ],
        },
    },
    {
        "version": "1.6.0",
        "date": "2026-10-06",
        "title": {
            "en": "Dashboard tabs: Needs reply, Events, Other mail",
            "fa": "تب‌های داشبورد: نیازمند جواب، رویدادها، سایر ایمیل‌ها",
        },
        "changes": {
            "en": [
                "The dashboard now has five tabs with counts: Needs reply, Events, Other mail, Sent and Rejected.",
                "New Events tab: all upcoming events found in any email, sorted by date. Each one is the usual editable card with an end date, location, an \"Open invite link\" button, a link back to its email and calendar conflict warnings. Adding or dismissing an event brings you back to this tab.",
                "New Other mail tab: emails that need no reply, each with its category and a one-line summary. \"Done\" archives it here only (Gmail is not touched), and \"Draft a reply anyway\" writes a draft that still waits for your approval. Archived mail can be shown and moved back.",
                "A failed draft now appears under Needs reply, and the old links to the previous tabs still work.",
                "A calendar invitation is never offered for events that come from newsletters or forwarded emails.",
                "The event cards fit narrow phone screens.",
            ],
            "fa": [
                "داشبورد حالا پنج تب با شمارنده دارد: نیازمند جواب، رویدادها، سایر ایمیل‌ها، ارسال‌شده و ردشده.",
                "تب تازه‌ی رویدادها: همه‌ی رویدادهای آینده که در هر ایمیلی پیدا شده، مرتب‌شده بر اساس تاریخ. هر کدام همان کارت قابل‌ویرایش است با تاریخ پایان، مکان، دکمه‌ی «باز کردن لینک دعوت»، لینک به ایمیل مربوط و هشدار تداخل تقویم. بعد از افزودن یا رد کردن یک رویداد به همین تب برمی‌گردی.",
                "تب تازه‌ی سایر ایمیل‌ها: ایمیل‌هایی که جواب نمی‌خواهند، هرکدام با دسته و خلاصه‌ی یک‌خطی. «انجام شد» فقط همین‌جا بایگانی می‌کند (جیمیل دست‌نخورده می‌ماند) و «با این حال جواب بنویس» پیش‌نویسی می‌نویسد که باز هم منتظر تأیید تو می‌ماند. ایمیل‌های بایگانی‌شده را می‌شود دید و برگرداند.",
                "پیش‌نویس ناموفق حالا زیر «نیازمند جواب» دیده می‌شود و لینک‌های قدیمی تب‌های قبلی هم کار می‌کنند.",
                "برای رویدادهایی که از خبرنامه یا ایمیل فورواردشده آمده‌اند دیگر پیشنهاد دعوت‌نامه‌ی تقویم داده نمی‌شود.",
                "کارت‌های رویداد روی صفحه‌ی باریک موبایل جا می‌شوند.",
            ],
        },
    },
    {
        "version": "1.5.0",
        "date": "2026-10-06",
        "title": {
            "en": "Every email is read, not only the ones that need a reply",
            "fa": "همه‌ی ایمیل‌ها خوانده می‌شوند، نه فقط ایمیل‌هایی که جواب می‌خواهند",
        },
        "changes": {
            "en": [
                "Every new email is now read once by a cheap AI model that sorts it (needs a reply, event invitation, information, newsletter, receipt, other), writes a one-line summary and finds events, deadlines and related events.",
                "A reply is drafted only when a real person is waiting for an answer. Newsletters, automated mail and forwarded messages never get a draft. Emails that need no reply appear under the new \"Other mail\" tab.",
                "Newsletters and automated mail are no longer ignored: they are still read for events and summaries (turn it off with PROCESS_BULK=false). The default Gmail search no longer excludes the Promotions, Updates, Social and Forums tabs.",
                "Better events: multi-day events (end date), the invitation link with an \"Open invite link\" button, cancelled events are shown as cancelled and cannot be added, cleaner titles and descriptions, and conflicting dates or times in one email are flagged.",
                "The same event arriving twice (invitation, reminder, forward) is shown only once, matched by its link or by its title and date.",
                "For forwarded emails the original sender, subject and date are read from inside the message. Other events mentioned only by name are listed without dates.",
                "Cost controls: a per-run limit for emails and a smaller one for bulk mail, a configurable cheap model (CLASSIFY_MODEL) and an optional blocked-senders list (SKIP_SENDERS).",
                "Safety: email text is treated as untrusted data. The AI has no tools, its answers are validated, links are only displayed and never opened, and nothing is sent or added to the calendar without your approval.",
                "The database gains new columns automatically when the app starts. Nothing is deleted.",
            ],
            "fa": [
                "هر ایمیل جدید یک بار توسط یک مدل هوش مصنوعی ارزان خوانده می‌شود: نوع آن (نیازمند جواب، دعوت به رویداد، اطلاع‌رسانی، خبرنامه، رسید، سایر) مشخص می‌شود، یک خلاصه‌ی یک‌خطی نوشته می‌شود و قرارها، مهلت‌ها و رویدادهای مرتبط پیدا می‌شوند.",
                "فقط وقتی یک آدم واقعی منتظر جواب است پیش‌نویس جواب نوشته می‌شود. برای خبرنامه‌ها، ایمیل‌های خودکار و ایمیل‌های فورواردشده هرگز پیش‌نویس نوشته نمی‌شود. ایمیل‌هایی که جواب نمی‌خواهند در بخش تازه‌ی «سایر ایمیل‌ها» دیده می‌شوند.",
                "خبرنامه‌ها و ایمیل‌های خودکار دیگر نادیده گرفته نمی‌شوند: برای پیدا کردن قرار و نوشتن خلاصه خوانده می‌شوند (با PROCESS_BULK=false خاموش می‌شود). جست‌وجوی پیش‌فرض جیمیل هم دیگر دسته‌های Promotions، Updates، Social و Forums را کنار نمی‌گذارد.",
                "قرارهای بهتر: رویداد چندروزه (تاریخ پایان)، لینک دعوت با دکمه‌ی «باز کردن لینک دعوت»، نمایش قرارهای لغوشده (که قابل افزودن نیستند)، عنوان و توضیح تمیزتر، و هشدار وقتی یک ایمیل تاریخ یا ساعت‌های ناسازگار می‌دهد.",
                "اگر یک قرار دو بار برسد (دعوت، یادآوری، فوروارد) فقط یک بار نشان داده می‌شود؛ با لینک یا با عنوان و تاریخ تشخیص داده می‌شود.",
                "برای ایمیل‌های فورواردشده، فرستنده، موضوع و تاریخ اصلی از داخل متن خوانده می‌شود. رویدادهای دیگری که فقط نامشان آمده بدون تاریخ فهرست می‌شوند.",
                "کنترل هزینه: سقف تعداد ایمیل در هر بار بررسی و سقف کمتر برای خبرنامه‌ها، مدل ارزان قابل تنظیم (CLASSIFY_MODEL) و فهرست اختیاری فرستنده‌های نادیده‌گرفته‌شده (SKIP_SENDERS).",
                "امنیت: متن ایمیل داده‌ی غیرقابل‌اعتماد حساب می‌شود. هوش مصنوعی ابزاری ندارد، جواب‌هایش بررسی می‌شود، لینک‌ها فقط نمایش داده می‌شوند و هرگز باز نمی‌شوند، و بدون تأیید تو چیزی ارسال یا به تقویم اضافه نمی‌شود.",
                "ستون‌های تازه‌ی دیتابیس هنگام شروع برنامه خودکار اضافه می‌شوند. چیزی پاک نمی‌شود.",
            ],
        },
    },
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
